# ===============================================================
#  calendar_app/llm.py
#  Natural language → structured calendar command using LLaMA + Pydantic
#
#  FLOW OVERVIEW:
#  Step 1 → User sends a plain-English prompt (e.g., "Schedule gym at 7am tomorrow")
#  Step 2 → extract_command() builds a system prompt with rules + current time
#  Step 3 → LLaMA 3.2 returns a JSON object matching CalendarCommand schema
#  Step 4 → Pydantic validates and normalizes the parsed JSON
#  Step 5 → Datetime strings are normalized to full ISO format with timezone
#  Step 6 → CalendarCommand is returned to the view for dispatch
# ===============================================================


# ---------------- Step 0: Imports & Config ----------------
import json
from typing import Optional, Literal
from datetime import datetime, timedelta

from pydantic import BaseModel, Field     # Schema definition + validation
from dateutil import parser as dateparser  # Parses many datetime string formats flexibly
from dateutil import tz                    # Timezone-aware datetime handling

from langchain_ollama import ChatOllama   # LangChain wrapper for local Ollama models

# Default timezone for the system — all events use this unless the user specifies another
DEFAULT_TZ = "Asia/Kathmandu"


# ================================================================
#  Pydantic Model: CalendarCommand
#  Represents the structured output that LLaMA must produce
#  Pydantic enforces types and provides model_validate() for safe parsing
#
#  action → what to do (create / update / delete / list)
#  The remaining fields are populated depending on the action
# ================================================================
class CalendarCommand(BaseModel):

    # ---------------- Step 1a: Action (Required) ----------------
    # LLaMA must always output one of these four values
    action: Literal["create", "update", "delete", "list"] = Field(
        description="What to do"
    )

    # ---------------- Step 1b: Event Identification (update/delete) ----------------
    # event_id → used when the user provides a specific Google event ID
    # query    → used when the user describes the event by title/description for search
    event_id: Optional[str] = Field(default=None, description="Google Calendar event id if known")
    query: Optional[str] = Field(default=None, description="Search query to find an event by title")

    # ---------------- Step 1c: Event Content Fields (create/update) ----------------
    summary: Optional[str] = Field(default=None, description="Event title")
    description: Optional[str] = Field(default="", description="Event notes/description")
    location: Optional[str] = Field(default="", description="Event location")

    # ---------------- Step 1d: Datetime Fields ----------------
    # LLaMA outputs RFC3339-like strings; _ensure_tz_iso() normalizes them
    start_iso: Optional[str] = Field(default=None, description="RFC3339-like start datetime")
    end_iso: Optional[str] = Field(default=None, description="RFC3339-like end datetime")

    # ---------------- Step 1e: Timezone ----------------
    # IANA timezone name — defaults to DEFAULT_TZ (Asia/Kathmandu)
    timeZone: str = Field(default=DEFAULT_TZ, description="IANA time zone name, e.g. Asia/Kathmandu")


# ================================================================
#  Helper 1: _ensure_tz_iso
#  Normalizes any datetime string into a full ISO 8601 string with timezone
#
#  Why needed? LLaMA may output "2024-12-25 10:00" (no tz) or
#  "2024-12-25T10:00:00+05:45" (with tz). Google Calendar API requires
#  the full timezone-aware ISO format. This function handles both cases.
# ================================================================
def _ensure_tz_iso(dt_str: str, tz_name: str) -> str:
    # dateparser.parse() is flexible — handles "tomorrow 10am", "2024-12-25 14:00", etc.
    dt = dateparser.parse(dt_str)
    # Resolve the timezone name to a tzinfo object (falls back to DEFAULT_TZ if invalid)
    zone = tz.gettz(tz_name) or tz.gettz(DEFAULT_TZ)

    # If the parsed datetime has no timezone, attach the resolved zone
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zone)

    return dt.isoformat()  # e.g., "2024-12-25T10:00:00+05:45"


# ================================================================
#  Helper 2: _default_end
#  When LLaMA provides a start time but no end time,
#  default the event duration to 1 hour
#  Google Calendar requires an end time — it cannot be omitted
# ================================================================
def _default_end(start_iso: str) -> str:
    start_dt = dateparser.parse(start_iso)
    return (start_dt + timedelta(hours=1)).isoformat()


# ================================================================
#  Main Function: extract_command
#  Converts a plain-English user prompt into a validated CalendarCommand
#
#  Flow:
#   Step 1 → Build a detailed system prompt with action rules + current time
#   Step 2 → Send to LLaMA 3.2 via Ollama (temperature=0 for deterministic output)
#   Step 3 → Parse LLaMA's raw JSON response
#   Step 4 → Validate against CalendarCommand schema using Pydantic
#   Step 5 → Normalize all datetime strings to full ISO with timezone
#   Step 6 → Fill in missing end time if start is provided
# ================================================================
def extract_command(prompt: str) -> CalendarCommand:
    # ---------------- Step 1: Build System Prompt ----------------
    # We inject the current local time so LLaMA can resolve relative terms
    # like "tomorrow", "next Monday", "in 3 hours" correctly
    now = datetime.now(tz=tz.gettz(DEFAULT_TZ))

    system = (
        "You are a calendar command parser.\n"
        "Return ONLY JSON. No markdown. No extra text.\n"
        "You must match the provided JSON schema.\n"
        "\n"
        "Rules:\n"
        "- action must be one of: create, update, delete, list.\n"
        "- If user says create/add/schedule -> action=create.\n"
        "- If user says delete/remove/cancel -> action=delete.\n"
        "- If user says update/edit/change -> action=update.\n"
        "- If user says list/show -> action=list.\n"
        "\n"
        "- If time is missing but date exists for create: default to 10:00 AM local time.\n"
        "- If end time missing for create/update with start time: end = start + 1 hour.\n"
        "- Prefer a clean summary title (e.g. 'Google Meet', 'Gym workout', 'Dentist appointment').\n"
        "- If user gives 'event id', put it in event_id.\n"
        "- For delete/update when event_id is not known, fill query with the best title-like text to search.\n"
        f"- Current local datetime is {now.isoformat()} and local timezone is {DEFAULT_TZ}.\n"
    )

    # ---------------- Step 2: Initialize LLaMA ----------------
    # temperature=0 → deterministic output, reduces hallucination in structured JSON tasks
    model = ChatOllama(model="llama3.2:3b", temperature=0)

    # ---------------- Step 3: Build the JSON Schema Hint ----------------
    # Providing the Pydantic schema directly in the prompt helps LLaMA
    # output JSON that matches the expected field names and types
    schema = CalendarCommand.model_json_schema()

    # ---------------- Step 4: Invoke LLaMA ----------------
    # Three-message format:
    #  [system] → parsing rules + current time context
    #  [user]   → the actual user prompt
    #  [user]   → the Pydantic JSON schema for LLaMA to follow
    resp = model.invoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
            {"role": "user", "content": "JSON_SCHEMA:\n" + json.dumps(schema)},
        ]
    )

    raw = resp.content.strip()  # LLaMA's raw response — should be valid JSON

    # ---------------- Step 5: Parse + Validate ----------------
    # json.loads() raises JSONDecodeError if LLaMA returns non-JSON (caught in the view)
    # model_validate() enforces the CalendarCommand schema and raises ValidationError if invalid
    data = json.loads(raw)
    cmd = CalendarCommand.model_validate(data)

    # ---------------- Step 6: Normalize Datetimes ----------------
    tz_name = cmd.timeZone or DEFAULT_TZ

    # Ensure both datetime strings are fully timezone-aware ISO strings
    if cmd.start_iso:
        cmd.start_iso = _ensure_tz_iso(cmd.start_iso, tz_name)
    if cmd.end_iso:
        cmd.end_iso = _ensure_tz_iso(cmd.end_iso, tz_name)

    # ---------------- Step 7: Fill Default End Time ----------------
    # Google Calendar API rejects events without an end time
    # If start is given but end is missing → auto-set end = start + 1 hour
    if cmd.action in ("create", "update"):
        if cmd.start_iso and not cmd.end_iso:
            cmd.end_iso = _default_end(cmd.start_iso)

    return cmd