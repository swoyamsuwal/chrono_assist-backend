from rest_framework import serializers
from .models import Document

class DocumentSerializer(serializers.ModelSerializer):
    original_filename = serializers.CharField(required=False, allow_blank=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "file",
            "file_url",              # include new field
            "original_filename",
            "mime_type",
            "file_size",
            "follow_group",
            "is_embedded", 
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "mime_type", "file_size", "file_url", "is_embedded"]

    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url  # S3/MinIO URL
        return None

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user
        file_obj = validated_data["file"]
        validated_data["original_filename"] = file_obj.name
        validated_data["mime_type"] = getattr(file_obj, "content_type", "")
        validated_data["file_size"] = file_obj.size
        validated_data["user"] = user
        validated_data["follow_group"] = user.follow_user.id if user.follow_user else user.id
        return super().create(validated_data)