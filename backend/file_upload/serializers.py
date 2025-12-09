from rest_framework import serializers
from .models import Document

class DocumentSerializer(serializers.ModelSerializer):
    # allow frontend to override name; if empty, we use file.name
    original_filename = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "file",
            "original_filename",
            "mime_type",
            "file_size",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "mime_type", "file_size"]

    def create(self, validated_data):
        file_obj = validated_data["file"]
        name = validated_data.get("original_filename") or file_obj.name

        validated_data["original_filename"] = name
        validated_data["mime_type"] = getattr(file_obj, "content_type", "")
        validated_data["file_size"] = file_obj.size

        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            raise serializers.ValidationError("User must be authenticated to upload.")
        validated_data["user"] = request.user

        return super().create(validated_data)
