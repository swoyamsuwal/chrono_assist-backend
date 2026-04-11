# ===============================================================
#  file_upload/views.py
#  All API views for file management and RAG (Retrieval-Augmented Generation)
#
#  VIEW OVERVIEW:
#  1. list_files      → GET  all documents in the user's company group
#  2. upload_file     → POST upload a new file to MinIO
#  3. delete_file     → DELETE a file (owner only)
#  4. embed_file      → POST trigger the embedding pipeline for a document
#  5. rag_chat        → POST ask a question across ALL embedded docs in the group
#  6. preview_file    → GET  generate a 10-min MinIO presigned URL
#  7. doc_chat        → POST ask a question scoped to ONE specific document
#
#  RAG HELPER FUNCTIONS (internal, not views):
#  - embed_query          → convert a question string into a vector
#  - search_similar_chunks→ find top-K closest chunks in pgvector
#  - build_prompt         → assemble context + history into a LLaMA prompt
# ===============================================================


# ---------------- Step 0: Imports & Config ----------------
from rest_framework.decorators import api_view, permission_classes, parser_classes
from .rbac_perms import CanViewFiles, CanUploadFiles, CanDeleteFiles, CanEmbedFiles, CanRagChat
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser  # Required for file upload parsing
from rest_framework.response import Response
from rest_framework import status
from pgvector.django import CosineDistance  # Annotates chunks with their vector distance from the query

from .models import Document, DocumentChunk
from .serializers import DocumentSerializer
from .embedding_file import create_embeddings_for_document  # Full embedding pipeline
from .utils import get_group_id  # Resolves company group_id for any user
from ollama import Client  # Local Ollama client for LLaMA inference

import boto3
from django.conf import settings

# ---------------- RAG Model Config ----------------
# These two models must be pulled in Ollama before the RAG features work:
#   ollama pull all-minilm:l6-v2   (embedding)
#   ollama pull llama3.2:3b        (generation)
EMBEDDING_MODEL_NAME = "all-minilm:l6-v2"  # Converts text to 384-dim vectors
LLM_MODEL_NAME = "llama3.2:3b"             # Generates natural language answers from context


# ================================================================
#  View 1: list_files
#  GET /list_files/
#  Returns all documents belonging to the current user's company group
#  Requires: IsAuthenticated + CanViewFiles (files:view RBAC check)
# ================================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated, CanViewFiles])
def list_files(request):
    # ---------------- Step 1: Resolve Company Group ----------------
    # group_id scopes the query — user only sees their company's files
    group_id = get_group_id(request.user)

    # ---------------- Step 2: Query Documents ----------------
    # Newest first (ordered by -created_at in model Meta)
    docs = (
        Document.objects
        .filter(follow_group=group_id)
        .order_by("-created_at")
    )

    serializer = DocumentSerializer(docs, many=True)
    return Response(serializer.data)


# ================================================================
#  View 2: upload_file
#  POST /upload_file/
#  Accepts multipart form data with a file field
#  Serializer auto-fills: original_filename, mime_type, file_size, follow_group, user
#  Requires: IsAuthenticated + CanUploadFiles (files:create RBAC check)
# ================================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated, CanUploadFiles])
@parser_classes([MultiPartParser, FormParser])  # Needed to handle multipart/form-data file uploads
def upload_file(request):
    # ---------------- Step 1: Validate + Save ----------------
    # context={"request": request} → serializer.create() uses request.user to fill user & follow_group
    serializer = DocumentSerializer(data=request.data, context={"request": request})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ================================================================
#  View 3: delete_file
#  DELETE /delete_file/
#  Body: { "id": "<document UUID>" }
#  Only the uploader can delete their own document (doc.user = request.user)
#  Also deletes the actual file from MinIO before removing the DB row
#  Requires: IsAuthenticated + CanDeleteFiles (files:delete RBAC check)
# ================================================================
@api_view(["DELETE"])
@permission_classes([IsAuthenticated, CanDeleteFiles])
def delete_file(request):
    # ---------------- Step 1: Validate Input ----------------
    doc_id = request.data.get("id")
    if not doc_id:
        return Response({"error": "id is required."}, status=status.HTTP_400_BAD_REQUEST)

    # ---------------- Step 2: Ownership Check ----------------
    # user=request.user → prevents users from deleting other people's files
    # even if they're in the same company group
    try:
        doc = Document.objects.get(id=doc_id, user=request.user)
    except Document.DoesNotExist:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    # ---------------- Step 3: Delete File from MinIO + DB ----------------
    # doc.file.delete(save=False) → removes the object from MinIO bucket
    # save=False → don't trigger another save() after deletion
    # doc.delete()              → removes the DB row (also cascades to DocumentChunk rows)
    doc.file.delete(save=False)
    doc.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ================================================================
#  View 4: embed_file
#  POST /embed_file/
#  Body: { "id": "<document UUID>" }
#  Triggers the full embedding pipeline: extract → chunk → vectorize → store
#  Any user in the same company group can embed any file (not just the uploader)
#  Requires: IsAuthenticated (no explicit RBAC class here — consider adding CanEmbedFiles)
# ================================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def embed_file(request):
    # ---------------- Step 1: Validate Input ----------------
    doc_id = request.data.get("id")
    if not doc_id:
        return Response({"error": "id is required."}, status=status.HTTP_400_BAD_REQUEST)

    # ---------------- Step 2: Resolve Group + Fetch Document ----------------
    # Group-scoped lookup → any member of the company can embed group files
    group_id = get_group_id(request.user)
    try:
        doc = Document.objects.get(id=doc_id, follow_group=group_id)
    except Document.DoesNotExist:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    # ---------------- Step 3: Run Embedding Pipeline ----------------
    # create_embeddings_for_document() handles all steps:
    # extract text → chunk → Ollama embed → bulk insert DocumentChunk rows → mark is_embedded=True
    count = create_embeddings_for_document(doc)

    return Response(
        {
            "document_id": str(doc.id),
            "chunks_created": count,         # How many DocumentChunk rows were created
            "is_embedded": doc.is_embedded,  # Should be True after pipeline runs
        },
        status=status.HTTP_200_OK,
    )


# ================================================================
#  RAG Helper 1: embed_query
#  Converts a plain text question into a vector using the same
#  embedding model used to embed document chunks
#  The returned vector is used for CosineDistance similarity search
# ================================================================
def embed_query(text: str):
    client = Client()
    resp = client.embeddings(model=EMBEDDING_MODEL_NAME, prompt=text)
    return resp["embedding"]  # list[float] — 384 dimensions for all-minilm:l6-v2


# ================================================================
#  RAG Helper 2: search_similar_chunks
#  Finds the top-K document chunks most semantically similar to the query vector
#  Scoped to the user's company group AND only searches embedded documents
#
#  Uses pgvector CosineDistance annotation → lower distance = more similar
# ================================================================
def search_similar_chunks(user, query_vector, top_k=10):
    # ---------------- Step 1: Scope to Company Group ----------------
    # Only search chunks from this company's embedded documents
    group_id = get_group_id(user)

    # ---------------- Step 2: Vector Similarity Query ----------------
    # .annotate(distance=CosineDistance(...)) → adds a computed "distance" column
    # .order_by("distance") → closest chunks come first
    # [:top_k] → SQL LIMIT — only return the best matches
    qs = (
        DocumentChunk.objects
        .filter(document__follow_group=group_id, document__is_embedded=True)
        .annotate(distance=CosineDistance("embedding", query_vector))
        .order_by("distance")[:top_k]
    )

    # ---------------- Step 3: Serialize to Dict ----------------
    # Returns plain dicts so build_prompt() can consume them without ORM awareness
    results = []
    for c in qs:
        results.append({
            "id": str(c.id),
            "text": c.text,           # The text that will be injected as LLM context
            "document_id": str(c.document_id),
        })
    return results


# ================================================================
#  RAG Helper 3: build_prompt
#  Assembles the final prompt string sent to LLaMA
#
#  Structure:
#   - System instruction (answer only from context)
#   - Last 6 messages of conversation history (for multi-turn chat)
#   - Context: the top-K retrieved chunk texts
#   - The user's current question
# ================================================================
def build_prompt(question: str, chunks: list[dict], history: list[dict]):
    # ---------------- Step 1: Format Conversation History ----------------
    # Only the last 6 messages → keeps prompt size manageable
    history_text = ""
    for msg in history[-6:]:
        history_text += f"{msg['role'].upper()}: {msg['content']}\n"

    # ---------------- Step 2: Format Retrieved Chunks as Context ----------------
    # Each chunk is prefixed with "- " for readability in the prompt
    context = "\n\n".join(f"- {c['text']}" for c in chunks)

    # ---------------- Step 3: Assemble Prompt ----------------
    # "answer using ONLY the context" → prevents LLaMA from hallucinating outside the docs
    prompt = (
        "You are a helpful assistant. Answer using ONLY the context below.\n\n"
        f"Previous conversation:\n{history_text}\n\n"
        f"Context from documents:\n{context}\n\n"
        f"Question: {question}\n\n"
        "If the context is not enough, say you are not sure. "
        "Answer briefly and clearly."
    )
    return prompt


# ================================================================
#  View 5: rag_chat
#  POST /rag_chat/
#  Body: { "question": "...", "history": [...] }
#  Global RAG — searches ALL embedded documents in the company group
#
#  Flow:
#   Step 1 → Embed the question into a vector
#   Step 2 → Find top-10 most similar chunks across all group documents
#   Step 3 → Build a prompt with context + history
#   Step 4 → Ask LLaMA 3.2 to generate an answer
#  Requires: IsAuthenticated + CanRagChat (prompt:execute RBAC check)
# ================================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated, CanRagChat])
def rag_chat(request):
    data = request.data
    question = data.get("question", "").strip()
    history = data.get("history", []) or []

    if not question:
        return Response({"error": "question is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # ---------------- Step 1: Embed the Question ----------------
        query_vec = embed_query(question)

        # ---------------- Step 2: Retrieve Similar Chunks ----------------
        # Scoped to the user's company group automatically inside search_similar_chunks()
        chunks = search_similar_chunks(request.user, query_vec, top_k=10)

        if not chunks:
            # No embedded documents found for this company — tell user to embed first
            return Response({
                "answer": "No relevant documents found. Upload and embed some files first.",
                "chunks": []
            })

        # ---------------- Step 3: Build Prompt ----------------
        prompt = build_prompt(question, chunks, history)

        # ---------------- Step 4: Ask LLaMA ----------------
        client = Client()
        resp = client.chat(
            model=LLM_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = resp["message"]["content"]

        return Response({
            "answer": answer,
            "chunks": chunks,          # Returned so frontend can show "Sources" section
            "chunk_count": len(chunks)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"RAG failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ================================================================
#  View 6: preview_file
#  GET /preview_file/<document_id>/
#  Generates a temporary presigned MinIO URL so the client can
#  view or download the file without exposing permanent credentials
#
#  Why presigned URLs?
#  MinIO files are not public — they require authentication.
#  A presigned URL embeds a time-limited signature so the browser
#  can load the file directly from MinIO (bypasses Django for large files).
# ================================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def preview_file(request, document_id):
    # ---------------- Step 1: Fetch Document (Group Scoped) ----------------
    group_id = get_group_id(request.user)
    try:
        doc = Document.objects.get(id=document_id, follow_group=group_id)
    except Document.DoesNotExist:
        return Response({"error": "Document not found."}, status=404)

    # ---------------- Step 2: Create Boto3 S3 Client for MinIO ----------------
    # boto3 is used directly here (not django-storages) because we need
    # generate_presigned_url() which is not exposed via Django's File API
    # signature_version="s3v4" is required for MinIO compatibility
    s3_client = boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,         # MinIO endpoint (e.g., http://minio:9000)
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=boto3.session.Config(signature_version="s3v4"),
    )

    # ---------------- Step 3: Generate Presigned URL ----------------
    # "get_object" → the client can only GET this specific file, not write/delete
    # ExpiresIn=600 → URL is valid for 10 minutes, then becomes invalid
    # doc.file.name → the MinIO object key (e.g., "uploads/report.pdf")
    presigned_url = s3_client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key": doc.file.name,
        },
        ExpiresIn=600,  # 10 minutes
    )

    return Response({
        "url": presigned_url,          # Frontend uses this to render an iframe or download link
        "mime_type": doc.mime_type,    # Frontend needs this to pick the right viewer (PDF/image/etc.)
        "filename": doc.original_filename,
        "is_embedded": doc.is_embedded,  # Frontend can show "Embed" button if False
    })


# ================================================================
#  View 7: doc_chat
#  POST /doc_chat/
#  Body: { "document_id": "...", "question": "...", "history": [...] }
#  Document-scoped RAG — searches ONLY the chunks of a specific document
#  Useful for "chat with this file" use cases
#
#  Flow:
#   Step 1 → Validate document_id + question
#   Step 2 → Verify document exists, belongs to the group, and is embedded
#   Step 3 → Embed the question
#   Step 4 → Search ONLY this document's chunks (not the whole group)
#   Step 5 → Build prompt + ask LLaMA → return answer
#  Requires: IsAuthenticated + CanRagChat (prompt:execute RBAC check)
# ================================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated, CanRagChat])
def doc_chat(request):
    # ---------------- Step 1: Validate Input ----------------
    group_id    = get_group_id(request.user)
    document_id = request.data.get("document_id", "").strip()
    question    = request.data.get("question",    "").strip()
    history     = request.data.get("history",     []) or []

    if not document_id:
        return Response({"error": "document_id is required."}, status=400)
    if not question:
        return Response({"error": "question is required."}, status=400)

    # ---------------- Step 2: Verify Document ----------------
    # Three conditions must all be true:
    #  a) document ID matches
    #  b) document belongs to this company group (prevents cross-company access)
    #  c) document has been embedded (no chunks = no answers)
    try:
        doc = Document.objects.get(
            id=document_id,
            follow_group=group_id,
            is_embedded=True,
        )
    except Document.DoesNotExist:
        return Response(
            {"error": "Document not found or has not been embedded yet."},
            status=404,
        )

    try:
        # ---------------- Step 3: Embed the Question ----------------
        query_vector = embed_query(question)

        # ---------------- Step 4: Search ONLY This Document's Chunks ----------------
        # Key difference from rag_chat: .filter(document_id=doc.id) restricts
        # the vector search to chunks from this one file only
        qs = (
            DocumentChunk.objects
            .filter(document_id=doc.id)
            .annotate(distance=CosineDistance("embedding", query_vector))
            .order_by("distance")[:10]
        )

        if not qs.exists():
            return Response({"answer": "No content found for this document."})

        # ---------------- Step 5a: Convert QuerySet to Dict List ----------------
        # build_prompt() expects list[dict] with "text" key — same shape as search_similar_chunks()
        chunks = [
            {"id": str(c.id), "text": c.text, "document_id": str(c.document_id)}
            for c in qs
        ]

        # ---------------- Step 5b: Build Prompt + Ask LLaMA ----------------
        prompt = build_prompt(question, chunks, history)

        client = Client()
        resp = client.chat(
            model=LLM_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = resp["message"]["content"]

        return Response({
            "answer":       answer,
            "document_id":  str(doc.id),
            "filename":     doc.original_filename,
            "chunk_count":  len(chunks),
        }, status=200)

    except Exception as e:
        return Response(
            {"error": f"Doc chat failed: {str(e)}"},
            status=500,
        )