# ===============================================================
#  file_upload/models.py
#  Two models power the RAG (Retrieval-Augmented Generation) system:
#
#  Document      → stores the uploaded file metadata + MinIO file reference
#  DocumentChunk → stores split text segments + their pgvector embeddings
#
#  Relationship: one Document → many DocumentChunks (after embedding)
# ===============================================================


# ---------------- Step 0: Imports ----------------
import uuid
import mimetypes
from django.conf import settings
from django.db import models
from pgvector.django import VectorField   # PostgreSQL pgvector extension — stores float[] as a vector column
from storages.backends.s3boto3 import S3Boto3Storage  # Sends files to MinIO instead of local disk


# ---------------- Step 1: Storage Backend ----------------
# s3_storage routes Django FileField writes to MinIO (S3-compatible)
# Reused on the file field so all uploads land in the configured bucket
s3_storage = S3Boto3Storage()


# ================================================================
#  Model 1: Document
#  Represents ONE uploaded file in the system
#  Tracks ownership (user), company grouping (follow_group),
#  file metadata, and whether it has been embedded yet
# ================================================================
class Document(models.Model):

    # ---------------- Step 2a: Primary Key ----------------
    # UUID instead of integer ID — prevents sequential ID enumeration from the API
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ---------------- Step 2b: Ownership ----------------
    # Links the document to the user who uploaded it
    # CASCADE → when a user is deleted, their documents are also deleted
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="documents",
    )

    # ---------------- Step 2c: Company Group ----------------
    # follow_group mirrors the group_id concept from authapp
    # All users in the same company share the same follow_group value
    # This allows SUB users to see/embed/chat with files uploaded by their MAIN user
    follow_group = models.PositiveIntegerField(default=0)

    # ---------------- Step 2d: The Actual File ----------------
    # FileField backed by s3_storage → file bytes go to MinIO under "uploads/" folder
    # .file.name = the MinIO object key (used when generating presigned URLs)
    file = models.FileField(upload_to="uploads/", storage=s3_storage)

    # ---------------- Step 2e: File Metadata ----------------
    original_filename = models.CharField(max_length=255)  # Original name from the user's machine
    mime_type = models.CharField(max_length=255, blank=True)  # e.g., "application/pdf", "text/plain"
    file_size = models.IntegerField(null=True)  # Size in bytes
    is_embedded = models.BooleanField(default=False)  # True once DocumentChunks + vectors exist for this file

    # ---------------- Step 2f: Timestamps ----------------
    created_at = models.DateTimeField(auto_now_add=True)  # Set once on creation
    updated_at = models.DateTimeField(auto_now=True)       # Updated on every save()

    # ---------------- Step 2g: Auto-populate Metadata on Save ----------------
    # Overrides save() so mime_type, file_size, and original_filename
    # are always kept in sync with the actual file — no manual work needed
    def save(self, *args, **kwargs):
        if self.file:
            self.original_filename = self.file.name
            self.file_size = self.file.size
            # mimetypes.guess_type() tries to infer type from the filename extension
            # Falls back to "application/octet-stream" if it can't determine the type
            self.mime_type = (
                mimetypes.guess_type(self.file.name)[0] or "application/octet-stream"
            )
        super().save(*args, **kwargs)

    class Meta:
        db_table = "documents_document"
        ordering = ["-created_at"]  # Newest files appear first in queries

    def __str__(self):
        return f"{self.original_filename} ({self.id})"


# ================================================================
#  Model 2: DocumentChunk
#  Represents ONE text segment extracted from a Document
#  Each chunk has an associated vector embedding stored in pgvector
#
#  Flow: Document → embed_file API → create_embeddings_for_document()
#        → many DocumentChunk rows with their embeddings
#  Retrieval: CosineDistance query on DocumentChunk.embedding
# ================================================================
class DocumentChunk(models.Model):

    # ---------------- Step 3a: Primary Key ----------------
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ---------------- Step 3b: Parent Document ----------------
    # CASCADE → deleting a Document also deletes all its chunks automatically
    # related_name="chunks" → doc.chunks.all() returns all chunks for a document
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        db_column="document_id",
        related_name="chunks",
    )

    # ---------------- Step 3c: Chunk Position & Content ----------------
    # chunk_index tracks the order of this chunk within the document
    # text holds the raw text of this chunk (what gets searched and shown as context)
    chunk_index = models.IntegerField()
    text = models.TextField()

    # ---------------- Step 3d: Optional Metadata ----------------
    # JSON blob for storing extra info (page number, section title, etc.)
    # Currently not populated but reserved for future use
    metadata = models.JSONField(null=True, blank=True)

    # ---------------- Step 3e: Vector Embedding ----------------
    # VectorField is a pgvector column — stores the float[] output of the embedding model
    # CosineDistance queries run directly against this column using a pgvector index
    # null=True → field is empty until embed_file is called
    embedding = VectorField(null=True, blank=True)

    # ---------------- Step 3f: Embedding Provenance ----------------
    # Tracks which embedding model was used (e.g., "all-minilm:l6-v2")
    # Useful if you ever switch models — old chunks will show a different model name
    embedding_model = models.CharField(max_length=255)
    embedding_created_at = models.DateTimeField(null=True, blank=True)

    # ---------------- Step 3g: Timestamps ----------------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "documents_document_chunk"
        ordering = ["document", "chunk_index"]  # Chunks are ordered by document then position

    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.document_id}"