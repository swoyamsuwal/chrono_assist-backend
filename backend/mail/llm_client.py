# ===============================================================
#  mail/llm_client.py
#  LLaMA-powered email draft generator
#  Takes a user prompt + tone key → returns {subject, body} dict
#
#  FLOW:
#  Step 1 → Initialize LLaMA model (llama3.2:3b via Ollama)
#  Step 2 → Resolve tone key to a human-readable label
#  Step 3 → Build a strict JSON-output instruction prompt
#  Step 4 → Invoke LLaMA and parse the JSON response
#  Step 5 → Return {subject, body} (with fallback if JSON parsing fails)
# ===============================================================


# ---------------- Step 0: Imports ----------------
import json  # For parsing and validating the JSON response from LLaMA

from langchain_ollama import OllamaLLM  # LangChain wrapper for local Ollama models


# ---------------- Step 1: Initialize the LLM ----------------
# llama3.2:3b → larger than :1b, better writing quality for email generation
# Instantiated once at module level so the model isn't reloaded on every request
llm = OllamaLLM(model="llama3.2:3b")


# ---------------- Step 2: Tone Mappings ----------------
# Maps frontend tone keys to human-readable labels injected into the LLaMA prompt
# The label directly influences how LLaMA adjusts vocabulary, formality, and structure
TONE_MAP = {
    "angry_firm":           "Angry / Firm Tone",
    "general_professional": "General / Professional Tone",
    "sweet_polite":         "Sweet / Polite Tone",
}


# ================================================================
#  Main Function: generate_email_draft
#  Called by GenerateEmailView when the user requests an AI email draft
#
#  Args:
#   prompt   → user's description of the email situation/request
#   tone_key → one of the TONE_MAP keys from the frontend dropdown
#
#  Returns: { "subject": str, "body": str }
# ================================================================
def generate_email_draft(prompt: str, tone_key: str) -> dict:

    # ---------------- Step 3a: Resolve Tone ----------------
    # If the frontend sends an unrecognized key, fall back to professional tone
    tone_label = TONE_MAP.get(tone_key, "General / Professional Tone")

    # ---------------- Step 3b: Build Instruction Prompt ----------------
    # We explicitly instruct LLaMA to return ONLY valid JSON with exactly two keys
    # "No markdown, no extra text" → prevents LLaMA from wrapping the JSON in ```json blocks
    instruction = f"""
You are an assistant that writes emails.

User request:
{prompt}

Tone:
{tone_label}

Return ONLY valid JSON with exactly these keys:
- subject: string
- body: string

No markdown, no extra text.
""".strip()

    # ---------------- Step 3c: Invoke LLaMA ----------------
    # llm.invoke() sends the prompt to the local Ollama instance and returns a string
    response_text = llm.invoke(instruction)

    # ---------------- Step 3d: Parse JSON Response ----------------
    try:
        # Strict JSON parsing — works when LLaMA correctly returns {"subject": "...", "body": "..."}
        data = json.loads(response_text)
        subject = (data.get("subject") or "").strip()
        body    = (data.get("body")    or "").strip()

    except Exception:
        # ---------------- Step 3e: Fallback Handling ----------------
        # LLaMA occasionally returns plain text instead of JSON (especially on first load)
        # Fallback: use the raw response as the body so the user still gets something useful
        subject = "Regarding my request"
        body    = response_text.strip()

    # ---------------- Step 3f: Return Draft ----------------
    return {
        "subject": subject,
        "body": body,
    }