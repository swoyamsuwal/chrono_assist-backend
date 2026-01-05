from rest_framework import serializers
from .models import Document
from .utils import get_group_id  # NEW


class DocumentSerializer(serializers.ModelSerializer):
    original_filename = serializers.CharField(required=False, allow_blank=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "file",
            "file_url",
            "original_filename",
            "mime_type",
            "file_size",
            "follow_group",
            "is_embedded",
            "created_at",
        ]
        read_only_fields = [
            "id", "created_at", "mime_type", "file_size",
            "file_url", "is_embedded", "follow_group"
        ]

    def get_file_url(self, obj):
        return obj.file.url if obj.file else None

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user

        file_obj = validated_data["file"]
        validated_data["original_filename"] = file_obj.name
        validated_data["mime_type"] = getattr(file_obj, "content_type", "")
        validated_data["file_size"] = file_obj.size

        validated_data["user"] = user

        # OLD:
        # validated_data["follow_group"] = user.follow_user.id if user.follow_user else user.id

        # NEW (same meaning, cleaner, avoids extra query):
        validated_data["follow_group"] = get_group_id(user)

        return super().create(validated_data)
