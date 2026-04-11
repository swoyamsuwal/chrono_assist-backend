# ===============================================================
#  file_upload/serializers.py
#  Single serializer: DocumentSerializer
#  Handles reading Document rows (GET) and creating new ones (POST upload)
#  Automatically populates metadata fields (mime_type, file_size, group) on create
# ===============================================================


# ---------------- Step 0: Imports ----------------
from rest_framework import serializers
from .models import Document
from .utils import get_group_id  # Resolves which company group the user belongs to


# ================================================================
#  DocumentSerializer
#  Used by: list_files (read), upload_file (create)
#  Key behaviours:
#   - file_url is a computed field (MinIO URL)
#   - On create: auto-fills mime_type, file_size, user, follow_group
#   - follow_group and other metadata are read-only (client never sets them)
# ================================================================
class DocumentSerializer(serializers.ModelSerializer):

    # ---------------- Step 1: Extra Fields ----------------
    # original_filename → can be sent by client but not required (auto-filled from file in create)
    original_filename = serializers.CharField(required=False, allow_blank=True)
    # file_url → read-only computed field, returns the MinIO storage URL for the file
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
        # These fields are set by the server — client can never write them
        read_only_fields = [
            "id", "created_at", "mime_type", "file_size",
            "file_url", "is_embedded", "follow_group"
        ]

    # ---------------- Step 2: Compute File URL ----------------
    # Called automatically by DRF for the file_url field
    # Returns the MinIO storage URL (could be a presigned URL depending on storage config)
    def get_file_url(self, obj):
        return obj.file.url if obj.file else None

    # ---------------- Step 3: Custom Create Logic ----------------
    # Runs when upload_file view calls serializer.save()
    # Populates server-side fields from the uploaded file object and request context
    def create(self, validated_data):
        request = self.context.get("request")  # Injected by the view via context={"request": request}
        user = request.user

        # ---------------- Step 3a: Extract File Metadata ----------------
        file_obj = validated_data["file"]
        validated_data["original_filename"] = file_obj.name        # e.g., "report.pdf"
        validated_data["mime_type"] = getattr(file_obj, "content_type", "")  # from HTTP multipart header
        validated_data["file_size"] = file_obj.size                # bytes

        # ---------------- Step 3b: Link to User ----------------
        validated_data["user"] = user

        # ---------------- Step 3c: Set Company Group ----------------
        # follow_group scopes the document to the user's company
        # MAIN user → group_id = user.id
        # SUB user  → group_id = follow_user_id (their MAIN user's ID)
        validated_data["follow_group"] = get_group_id(user)

        return super().create(validated_data)