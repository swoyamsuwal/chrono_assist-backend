import json
from typing import Optional, Literal
from datetime import datetime, timedelta

from pydantic import BaseModel, Field
from dateutil import parser as dateparser
from dateutil import tz

from langchain_ollama import ChatOllama


DEFAULT_TZ = "Asia/Kathmandu"


class CalendarCommand(BaseModel):
    action: Literal["create", "update", "delete", "list"] = Field(
        description="What to do"
    )

    # Identification (update/delete)
    event_id: Optional[str] = Field(default=None, description="Google Calendar event id if known")
    query: Optional[str] = Field(default=None, description="Search query to find an event by title")

    # Event fields (create/update)
    summary: Optional[str] = Field(default=None, description="Event title")
    description: Optional[str] = Field(default="", description="Event notes/description")
    location: Optional[str] = Field(default="", description="Event location")

    # Use ISO datetime strings; include timezone offset if possible
    start_iso: Optional[str] = Field(default=None, description="RFC3339-like start datetime")
    end_iso: Optional[str] = Field(default=None, description="RFC3339-like end datetime")

    timeZone: str = Field(default=DEFAULT_TZ, description="IANA time zone name, e.g. Asia/Kathmandu")


def _ensure_tz_iso(dt_str: str, tz_name: str) -> str:
    """
    Accepts many datetime formats; returns ISO with timezone.
    If dt has no tzinfo, assumes tz_name.
    """
    dt = dateparser.parse(dt_str)
    zone = tz.gettz(tz_name) or tz.gettz(DEFAULT_TZ)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zone)
    return dt.isoformat()


def _default_end(start_iso: str) -> str:
    start_dt = dateparser.parse(start_iso)
    return (start_dt + timedelta(hours=1)).isoformat()


def extract_command(prompt: str) -> CalendarCommand:
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

    model = ChatOllama(model="llama3.2:3b", temperature=0)

    schema = CalendarCommand.model_json_schema()

    # Best effort: ask for schema-bound JSON
    resp = model.invoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
            {"role": "user", "content": "JSON_SCHEMA:\n" + json.dumps(schema)},
        ]
    )

    raw = resp.content.strip()

    # Parse JSON + validate
    data = json.loads(raw)
    cmd = CalendarCommand.model_validate(data)

    # Normalize timezone and datetimes
    tz_name = cmd.timeZone or DEFAULT_TZ

    if cmd.start_iso:
        cmd.start_iso = _ensure_tz_iso(cmd.start_iso, tz_name)

    if cmd.end_iso:
        cmd.end_iso = _ensure_tz_iso(cmd.end_iso, tz_name)

    # Defaults
    if cmd.action in ("create", "update"):
        if cmd.start_iso and not cmd.end_iso:
            cmd.end_iso = _default_end(cmd.start_iso)

    return cmd
