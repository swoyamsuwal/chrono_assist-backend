# ---------------- Step 0: Importing necessary libraries ----------------
import json  # For parsing and validating JSON responses from the LLM

# LangChain Ollama LLM
from langchain_ollama import OllamaLLM  # Ollama-based Large Language Model


# ---------------- Step 1: Initialize the LLM ----------------
# This model will be used to generate email drafts
# llama3.2:3b → slightly larger model for better writing quality
llm = OllamaLLM(model="llama3.2:3b")


# ---------------- Step 2: Define tone mappings ----------------
# These keys come from the frontend or API request
# Each key maps to a human-readable tone instruction
TONE_MAP = {
    "angry_firm": "Angry / Firm Tone",
    "general_professional": "General / Professional Tone",
    "sweet_polite": "Sweet / Polite Tone",
}


# ---------------- Step 3: Email generation function ----------------
def generate_email_draft(prompt: str, tone_key: str) -> dict:
    """
    Generates an email subject and body based on user input and tone.
    
    Args:
        prompt (str): User's email request or situation
        tone_key (str): Selected tone key from TONE_MAP

    Returns:
        dict: {
            "subject": string,
            "body": string
        }
    """

    # ---------------- Step 3a: Resolve tone ----------------
    # If the tone_key is invalid, fall back to professional tone
    tone_label = TONE_MAP.get(tone_key, "General / Professional Tone")

    # ---------------- Step 3b: Build LLM instruction ----------------
    # We force the model to return ONLY valid JSON
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

    # ---------------- Step 3c: Invoke the LLM ----------------
    # invoke() is the modern LangChain API
    response_text = llm.invoke(instruction)

    # ---------------- Step 3d: Parse LLM response safely ----------------
    try:
        # Try strict JSON parsing
        data = json.loads(response_text)

        subject = (data.get("subject") or "").strip()
        body = (data.get("body") or "").strip()

    except Exception:
        # ---------------- Step 3e: Fallback handling ----------------
        # If model fails to return valid JSON
        subject = "Regarding my request"
        body = response_text.strip()

    # ---------------- Step 3f: Return clean response ----------------
    return {
        "subject": subject,
        "body": body
    }
