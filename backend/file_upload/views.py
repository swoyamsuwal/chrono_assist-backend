from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from pgvector.django import CosineDistance 

from .models import Document, DocumentChunk
from .serializers import DocumentSerializer
from .embedding_file import create_embeddings_for_document
from ollama import Client
from django.db import connection
import json

# ---------------- RAG Configuration ----------------
EMBEDDING_MODEL_NAME = "all-minilm:l6-v2"
LLM_MODEL_NAME = "llama3.2:3b"

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_files(request):
    docs = Document.objects.filter(user=request.user).order_by("-created_at")
    serializer = DocumentSerializer(docs, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_file(request):
    serializer = DocumentSerializer(data=request.data, context={"request": request})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_file(request):
    """
    DELETE JSON body:
      - id: document UUID
    Only deletes documents owned by current user.
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
    doc_id = request.data.get("id")
    if not doc_id:
        return Response({"error": "id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        doc = Document.objects.get(id=doc_id, user=request.user)
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
    """Step 1: Convert question to embedding vector using Ollama"""
    client = Client()
    resp = client.embeddings(model=EMBEDDING_MODEL_NAME, prompt=text)
    return resp["embedding"]  # list[float]


def search_similar_chunks(user, query_vector, top_k=10):
    """
    Use pgvector's CosineDistance on the VectorField via Django ORM.
    Also print the top-k similar chunks' text to the terminal.
    """
    qs = (
        DocumentChunk.objects
        .filter(document__user=user, document__is_embedded=True)
        .annotate(distance=CosineDistance("embedding", query_vector))
        .order_by("distance")[:top_k]
    )

    results = []
    print("\n=== Top similar chunks ===")
    for idx, c in enumerate(qs):
        print(f"\n--- Chunk {idx + 1} ---")
        print(f"ID: {c.id}")
        print(f"Document ID: {c.document_id}")
        print(f"Distance: {getattr(c, 'distance', None)}")
        print("Text:")
        print(c.text)  # full text; change to c.text[:200] if too long

        results.append(
            {
                "id": str(c.id),
                "text": c.text,
                "document_id": str(c.document_id),
            }
        )

    if not results:
        print("No similar chunks found.")

    return results

def build_prompt(question: str, chunks: list[dict], history: list[dict]):
    # history is a list of {role, content}, like ChatGPT
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
@permission_classes([IsAuthenticated])
def rag_chat(request):
    """
    Step 4: Full RAG pipeline endpoint
    
    Input: {question: str, history: [{role, content}]}
    Output: {answer: str, chunks: [...]}
    """
    data = request.data
    question = data.get("question", "").strip()
    history = data.get("history", []) or []

    if not question:
        return Response({"error": "question is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Step 1: Embed the question
        query_vec = embed_query(question)

        # Step 2: Retrieve top-10 similar chunks for this user
        chunks = search_similar_chunks(request.user, query_vec, top_k=10)

        if not chunks:
            return Response({
                "answer": "No relevant documents found. Upload and embed some files first.",
                "chunks": []
            })

        # Step 3: Build RAG prompt
        prompt = build_prompt(question, chunks, history)

        # Step 4: Generate answer with Ollama
        client = Client()
        resp = client.chat(
            model=LLM_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = resp["message"]["content"]

        return Response({
            "answer": answer,
            "chunks": chunks,  # for debugging
            "chunk_count": len(chunks)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            "error": f"RAG failed: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


