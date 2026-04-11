# ===============================================================
#  file_upload/urls.py
#  URL routing for all file management and RAG endpoints
#  Mounted under a prefix (e.g., /api/files/) in the root urls.py
# ===============================================================


# ---------------- Step 0: Imports ----------------
from django.urls import path
from . import views


urlpatterns = [

    # ---------------- Step 1: File Management ----------------
    # GET  → list all documents belonging to the current user's company group
    path("list_files/", views.list_files, name="list_files"),

    # POST (multipart) → upload a new file; auto-fills metadata and group_id
    path("upload_file/", views.upload_file, name="upload_file"),

    # DELETE → remove a file from MinIO + DB (only the uploader can delete their own file)
    path("delete_file/", views.delete_file, name="delete_file"),

    # ---------------- Step 2: Embedding Pipeline ----------------
    # POST → triggers text extraction + chunking + Ollama embedding for a specific document
    # Must be called before rag_chat or doc_chat can use the document
    path("embed_file/", views.embed_file, name="embed_file"),

    # ---------------- Step 3: RAG Chat (Global) ----------------
    # POST → asks a question against ALL embedded documents in the company group
    # Embeds the question → retrieves top-K chunks → LLaMA generates an answer
    path("rag_chat/", views.rag_chat, name="rag_chat"),

    # ---------------- Step 4: File Preview ----------------
    # GET → generates a short-lived MinIO presigned URL for viewing/downloading a file
    # URL expires in 10 minutes — client renders it in an iframe or downloads it
    path("preview_file/<uuid:document_id>/", views.preview_file, name="preview_file"),

    # ---------------- Step 5: RAG Chat (Document-Scoped) ----------------
    # POST → same as rag_chat but restricted to a SINGLE document's chunks
    # Useful for "chat with this file" use cases
    path("doc_chat/", views.doc_chat, name="doc_chat"),
]