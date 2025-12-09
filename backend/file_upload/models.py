import uuid
from django.conf import settings
from django.db import models
from pgvector.django import VectorField

class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="documents",
    )
    file = models.FileField(upload_to="uploads/")  # stored in MinIO

    original_filename = models.CharField(max_length=255)

    mime_type = models.CharField(max_length=255)
    file_size = models.IntegerField()
    is_embedded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "documents_document"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.id})"


class DocumentChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        db_column="document_id",
        related_name="chunks",
    )

    chunk_index = models.IntegerField()
    text = models.TextField()
    metadata = models.JSONField(null=True, blank=True)
    embedding = VectorField(null=True, blank=True)
    embedding_model = models.CharField(max_length=255)
    embedding_created_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "documents_document_chunk"
        ordering = ["document", "chunk_index"]

    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.document_id}"
