from rest_framework.decorators import api_view, permission_classes, parser_classes
from .rbac_perms import CanViewFiles, CanUploadFiles, CanDeleteFiles, CanEmbedFiles, CanRagChat
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from pgvector.django import CosineDistance

from .models import Document, DocumentChunk
from .serializers import DocumentSerializer
from .embedding_file import create_embeddings_for_document
from .utils import get_group_id  # helper
from ollama import Client

import boto3
from django.conf import settings

# ---------------- RAG Configuration ----------------
EMBEDDING_MODEL_NAME = "all-minilm:l6-v2"
LLM_MODEL_NAME = "llama3.2:3b"


@api_view(["GET"])
@permission_classes([IsAuthenticated,CanViewFiles])
def list_files(request):
    group_id = get_group_id(request.user)

    docs = (
        Document.objects
        .filter(follow_group=group_id)
        .order_by("-created_at")
    )

    serializer = DocumentSerializer(docs, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated,CanUploadFiles])
@parser_classes([MultiPartParser, FormParser])
def upload_file(request):
    serializer = DocumentSerializer(data=request.data, context={"request": request})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated,CanDeleteFiles])
def delete_file(request):
    """
    DELETE JSON body:
      - id: document UUID

    Safer rule for group-sharing:
    - allow delete only if requester is the owner (same as you had)
    """
    doc_id = request.data.get("id")
    if not doc_id:
        return Response({"error": "id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        doc = Document.objects.get(id=doc_id, user=request.user)
    except Document.DoesNotExist:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    doc.file.delete(save=False)
    doc.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def embed_file(request):
    """
    If you want followers to embed files uploaded by anyone in the same group,
    fetch the doc by (id + follow_group), not (id + user).
    """
    doc_id = request.data.get("id")
    if not doc_id:
        return Response({"error": "id is required."}, status=status.HTTP_400_BAD_REQUEST)

    group_id = get_group_id(request.user)

    try:
        doc = Document.objects.get(id=doc_id, follow_group=group_id)
    except Document.DoesNotExist:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    count = create_embeddings_for_document(doc)

    return Response(
        {
            "document_id": str(doc.id),
            "chunks_created": count,
            "is_embedded": doc.is_embedded,
        },
        status=status.HTTP_200_OK,
    )


# ---------------- RAG Functions ----------------
def embed_query(text: str):
    client = Client()
    resp = client.embeddings(model=EMBEDDING_MODEL_NAME, prompt=text)
    return resp["embedding"]


def search_similar_chunks(user, query_vector, top_k=10):
    """
    Group-based retrieval:
    only search chunks belonging to documents with the same follow_group.
    """
    group_id = get_group_id(user)

    qs = (
        DocumentChunk.objects
        .filter(document__follow_group=group_id, document__is_embedded=True)
        .annotate(distance=CosineDistance("embedding", query_vector))
        .order_by("distance")[:top_k]
    )

    results = []
    for c in qs:
        results.append(
            {
                "id": str(c.id),
                "text": c.text,
                "document_id": str(c.document_id),
            }
        )
    return results


def build_prompt(question: str, chunks: list[dict], history: list[dict]):
    history_text = ""
    for msg in history[-6:]:
        history_text += f"{msg['role'].upper()}: {msg['content']}\n"

    context = "\n\n".join(f"- {c['text']}" for c in chunks)

    prompt = (
        "You are a helpful assistant. Answer using ONLY the context below.\n\n"
        f"Previous conversation:\n{history_text}\n\n"
        f"Context from documents:\n{context}\n\n"
        f"Question: {question}\n\n"
        "If the context is not enough, say you are not sure. "
        "Answer briefly and clearly."
    )
    return prompt


@api_view(["POST"])
@permission_classes([IsAuthenticated,CanRagChat])
def rag_chat(request):
    data = request.data
    question = data.get("question", "").strip()
    history = data.get("history", []) or []

    if not question:
        return Response({"error": "question is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        query_vec = embed_query(question)

        # now uses group retrieval internally
        chunks = search_similar_chunks(request.user, query_vec, top_k=10)

        if not chunks:
            return Response({
                "answer": "No relevant documents found. Upload and embed some files first.",
                "chunks": []
            })

        prompt = build_prompt(question, chunks, history)

        client = Client()
        resp = client.chat(
            model=LLM_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = resp["message"]["content"]

        return Response({
            "answer": answer,
            "chunks": chunks,
            "chunk_count": len(chunks)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"error": f"RAG failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ─────────────────────────────────────────────
# VIEW 1 : Generate presigned MinIO URL for preview
# ─────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def preview_file(request, document_id):
    group_id = get_group_id(request.user)

    try:
        doc = Document.objects.get(id=document_id, follow_group=group_id)
    except Document.DoesNotExist:
        return Response({"error": "Document not found."}, status=404)

    s3_client = boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=boto3.session.Config(signature_version="s3v4"),
    )

    presigned_url = s3_client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key": doc.file.name,
        },
        ExpiresIn=600,  # 10 minutes
    )

    return Response(
        {
            "url": presigned_url,
            "mime_type": doc.mime_type,
            "filename": doc.original_filename,
            "is_embedded": doc.is_embedded,
        }
    )


# ─────────────────────────────────────────────
# VIEW 2 : Document-scoped RAG chat
# ─────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([IsAuthenticated, CanRagChat])
def doc_chat(request):
    group_id    = get_group_id(request.user)
    document_id = request.data.get("document_id", "").strip()
    question    = request.data.get("question",    "").strip()
    history     = request.data.get("history",     []) or []

    if not document_id:
        return Response({"error": "document_id is required."}, status=400)
    if not question:
        return Response({"error": "question is required."}, status=400)

    # Guard: doc must exist, belong to this group, AND be embedded
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
        # 1. Embed the question
        query_vector = embed_query(question)

        # 2. Retrieve chunks ONLY from this one document (scoped by document_id)
        qs = (
            DocumentChunk.objects
            .filter(document_id=doc.id)
            .annotate(distance=CosineDistance("embedding", query_vector))
            .order_by("distance")[:10]
        )

        if not qs.exists():
            return Response({"answer": "No content found for this document."})

        # 3. Convert QuerySet → list[dict] so build_prompt() can consume it
        #    (same shape that search_similar_chunks() returns)
        chunks = [
            {"id": str(c.id), "text": c.text, "document_id": str(c.document_id)}
            for c in qs
        ]

        # 4. Build prompt using the existing helper
        prompt = build_prompt(question, chunks, history)

        # 5. Ask Ollama — same pattern as rag_chat
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

    group_id = get_group_id(request.user)
    document_id = request.data.get("document_id", "").strip()
    question    = request.data.get("question", "").strip()
    history     = request.data.get("history", [])

    if not document_id:
        return Response({"error": "document_id is required."}, status=400)
    if not question:
        return Response({"error": "question is required."}, status=400)

    # ── Guard: doc must exist, belong to this group, AND be embedded ──
    try:
        doc = Document.objects.get(
            id=document_id,
            follow_group=group_id,
            is_embedded=True,       # block non-embedded docs
        )
    except Document.DoesNotExist:
        return Response(
            {"error": "Document not found or has not been embedded yet."},
            status=404,
        )

    # ── Embed the question ──
    query_vector = embed_query(question)   # your existing helper

    # ── Retrieve chunks ONLY from this one document ──
    chunks = (
        DocumentChunk.objects.filter(document_id=doc.id)
        .annotate(distance=CosineDistance("embedding", query_vector))
        .order_by("distance")[:10]
    )

    if not chunks.exists():
        return Response({"answer": "No content found for this document."})

    # ── Build prompt (reuse your existing helper) ──
    answer = build_and_ask(question, chunks, history)   # your existing helper

    return Response(
        {
            "answer": answer,
            "document_id": str(doc.id),
            "filename": doc.original_filename,
            "chunk_count": chunks.count(),
        }
    )