from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status

from .models import Document
from .serializers import DocumentSerializer
from .embedding_file import create_embeddings_for_document

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
