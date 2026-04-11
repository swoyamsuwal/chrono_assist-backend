# ===============================================================
#  mail/serializers.py
#  Serializers for both one-on-one mail and bulk campaign features
#
#  One-on-one:
#   GenerateEmailSerializer → validates AI draft generation request
#   SendEmailSerializer     → validates direct single-recipient send
#
#  Bulk Campaign:
#   CampaignRecipientSerializer → read/write for individual recipients
#   EmailCampaignSerializer     → full campaign representation with computed fields
#   BulkSendSerializer          → validates subject+body for a one-off bulk send
# ===============================================================


# ---------------- Step 0: Imports ----------------
from rest_framework import serializers
from .models import EmailCampaign, CampaignRecipient


# ================================================================
#  Serializer 1: GenerateEmailSerializer
#  Used by: GenerateEmailView (POST /generate/)
#  Validates the prompt text and tone selection before passing to LLaMA
# ================================================================
class GenerateEmailSerializer(serializers.Serializer):
    # prompt → the user's description of the email they want written
    prompt = serializers.CharField()
    # tone  → must be one of the three keys that map to TONE_MAP in llm_client.py
    tone = serializers.ChoiceField(choices=[
        ("angry_firm",           "Angry / Firm Tone"),
        ("general_professional", "General / Professional Tone"),
        ("sweet_polite",         "Sweet / Polite Tone"),
    ])


# ================================================================
#  Serializer 2: SendEmailSerializer
#  Used by: SendEmailView (POST /send/)
#  Validates a direct one-on-one email send request
# ================================================================
class SendEmailSerializer(serializers.Serializer):
    recipient = serializers.EmailField()   # Validated email address
    subject   = serializers.CharField()
    body      = serializers.CharField()


# ================================================================
#  Serializer 3: CampaignRecipientSerializer
#  Used by: CampaignRecipientsView, CampaignRecipientDetailView
#  Serializes a single recipient row — used both for listing and nested in campaigns
# ================================================================
class CampaignRecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CampaignRecipient
        fields = ["id", "email", "name"]


# ================================================================
#  Serializer 4: EmailCampaignSerializer
#  Used by: CampaignListCreateView, CampaignDetailView
#  Full campaign representation including nested recipients and computed fields
# ================================================================
class EmailCampaignSerializer(serializers.ModelSerializer):

    # ---------------- Step 4a: Nested Recipients ----------------
    # read_only=True → recipients are managed via their own endpoint, not here
    recipients = CampaignRecipientSerializer(many=True, read_only=True)

    # ---------------- Step 4b: Computed Fields ----------------
    # recipient_count → how many email addresses are in this campaign
    recipient_count = serializers.SerializerMethodField()
    # has_draft → True if both subject AND body are filled in (ready to send)
    has_draft = serializers.SerializerMethodField()

    class Meta:
        model  = EmailCampaign
        fields = [
            "id", "name", "subject", "body",
            "has_draft", "recipient_count", "recipients",
            "created_at", "updated_at",
        ]

    # ---------------- Step 4c: Compute recipient_count ----------------
    def get_recipient_count(self, obj):
        return obj.recipients.count()

    # ---------------- Step 4d: Compute has_draft ----------------
    # Frontend uses this to decide whether to show a "Send" button or "Write draft first" prompt
    def get_has_draft(self, obj):
        return bool(obj.subject and obj.body)


# ================================================================
#  Serializer 5: BulkSendSerializer
#  Used by: CampaignBulkSendView (POST /campaigns/<pk>/send/)
#  Validates subject + body for a one-off send (override the saved draft)
#  NOTE: Currently unused — the view reads subject/body from the saved campaign draft
# ================================================================
class BulkSendSerializer(serializers.Serializer):
    subject = serializers.CharField()
    body    = serializers.CharField()