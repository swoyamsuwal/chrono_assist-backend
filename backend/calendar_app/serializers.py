# ===============================================================
#  calendar_app/serializers.py
#  Single serializer for validating the AI prompt endpoint input
#  Keeps the view clean — prompt validation happens here, not in the view
# ===============================================================


# ---------------- Step 0: Imports ----------------
from rest_framework import serializers


# ================================================================
#  PromptSerializer
#  Used by: ai_prompt_handler view (POST /ai-prompt/)
#  Validates that the request body contains a non-empty "prompt" string
#  The validated prompt is then passed to extract_command() in llm.py
# ================================================================
class PromptSerializer(serializers.Serializer):
    # prompt → the natural language instruction from the user
    # e.g., "Schedule a team meeting tomorrow at 3pm"
    prompt = serializers.CharField()