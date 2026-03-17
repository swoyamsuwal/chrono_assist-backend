from rest_framework import serializers
from .models import EmailCampaign, CampaignRecipient


# ── Existing (unchanged) ──────────────────────────────────────────────────────

class GenerateEmailSerializer(serializers.Serializer):
    prompt = serializers.CharField()
    tone = serializers.ChoiceField(choices=[
        ("angry_firm",           "Angry / Firm Tone"),
        ("general_professional", "General / Professional Tone"),
        ("sweet_polite",         "Sweet / Polite Tone"),
    ])


class SendEmailSerializer(serializers.Serializer):
    recipient = serializers.EmailField()
    subject   = serializers.CharField()
    body      = serializers.CharField()


# ── Campaign ──────────────────────────────────────────────────────────────────

class CampaignRecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CampaignRecipient
        fields = ["id", "email", "name"]


class EmailCampaignSerializer(serializers.ModelSerializer):
    recipients      = CampaignRecipientSerializer(many=True, read_only=True)
    recipient_count = serializers.SerializerMethodField()
    has_draft       = serializers.SerializerMethodField()

    class Meta:
        model  = EmailCampaign
        fields = [
            "id",
            "name",
            "subject",
            "body",
            "has_draft",
            "recipient_count",
            "recipients",
            "created_at",
            "updated_at",
        ]

    def get_recipient_count(self, obj):
        return obj.recipients.count()

    def get_has_draft(self, obj):
        return bool(obj.subject and obj.body)


class BulkSendSerializer(serializers.Serializer):
    subject = serializers.CharField()
    body    = serializers.CharField()
