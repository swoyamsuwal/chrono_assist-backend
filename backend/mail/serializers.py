from rest_framework import serializers


class GenerateEmailSerializer(serializers.Serializer):
    prompt = serializers.CharField()
    tone = serializers.ChoiceField(choices=[
        ("angry_firm", "Angry / Firm Tone"),
        ("general_professional", "General / Professional Tone"),
        ("sweet_polite", "Sweet / Polite Tone"),
    ])


class SendEmailSerializer(serializers.Serializer):
    recipient = serializers.EmailField()
    subject = serializers.CharField()
    body = serializers.CharField()
