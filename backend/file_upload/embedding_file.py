# ---------------- Step 0: Imports & config ----------------
import os
import tempfile

# File parsers for different formats
from pypdf import PdfReader                # PDF reader
from docx import Document as DocxDocument  # DOCX reader
from pptx import Presentation              # PPTX reader

# LangChain text splitter (for chunking long documents)
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Ollama Python client (for embeddings with all-minilm:l6-v2)
from ollama import Client

# Django models
from .models import Document, DocumentChunk

# Ollama host comes from env (example: http://localhost:11434)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
# Name of the embedding model in Ollama
EMBEDDING_MODEL_NAME = "all-minilm:l6-v2"


# ---------------- Step 1: Extract text from Django FileField ----------------
def extract_text_from_fileobj(django_file, mime_type: str) -> str:
    """
    Take a Django FileField (doc.file) and its mime_type,
    write it to a temporary file, then pass that path to the
    actual parser function (PDF/DOCX/PPTX/TXT).
    """

    # Decide file suffix from original filename, so parsers know the type
    suffix = "." + (django_file.name.split(".")[-1] if "." in django_file.name else "")

    # Create a real temp file on disk and stream the Django file content into it
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        for chunk in django_file.chunks():
            tmp.write(chunk)
        temp_path = tmp.name  # path to the temp file we just wrote

    # Now parse that temp file according to mime/extension
    try:
        return extract_text_from_path(temp_path, mime_type)
    finally:
        # Clean up the temp file after parsing
        try:
            os.remove(temp_path)
        except OSError:
            pass


# ---------------- Step 2: Extract text from a file path ----------------
def extract_text_from_path(file_path: str, mime_type: str) -> str:
    """
    Given a local file path + mime_type, detect format and extract text.
    Supports: PDF, DOCX, PPTX, TXT (fallback).
    """
    mime_type = (mime_type or "").lower()
    ext = os.path.splitext(file_path)[1].lower()

    # ----- PDF -----
    if "pdf" in mime_type or ext == ".pdf":
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    # ----- DOCX -----
    if "word" in mime_type or ext in (".docx",):
        doc = DocxDocument(file_path)
        return "\n".join(p.text for p in doc.paragraphs)

    # ----- PPTX -----
    if "ppt" in mime_type or ext in (".pptx",):
        pres = Presentation(file_path)
        texts = []
        for slide in pres.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    texts.append(shape.text)
        return "\n".join(texts)

    # ----- TXT / fallback -----
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


# ---------------- Step 3: Chunk long text ----------------
def chunk_text(text: str):
    """
    Split a long text into overlapping chunks so embeddings
    keep enough context.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,   # max chars per chunk
        chunk_overlap=200, # overlap between chunks
        length_function=len,
    )
    return splitter.split_text(text)  # returns list[str]


# ---------------- Step 4: Create embeddings with Ollama ----------------
def embed_chunks(chunks):
    """
    Send each chunk to Ollama to get an embedding vector.
    Uses OLLAMA_HOST from environment; we do NOT pass base_url here
    to avoid httpx 'multiple values for base_url' bug.
    """
    # OLLAMA_HOST is read by the client internally
    client = Client()

    embeddings = []
    for chunk in chunks:
        # client.embeddings returns a dict with 'embedding' key (list[float])
        resp = client.embeddings(model=EMBEDDING_MODEL_NAME, prompt=chunk)
        embeddings.append(resp["embedding"])
    return embeddings  # list[list[float]]


# ---------------- Step 5: Full pipeline for a single Document ----------------
def create_embeddings_for_document(doc: Document):
    """
    High-level pipeline for one Document row:

    1. Read file from Django storage (MinIO-backed FileField).
    2. Extract raw text depending on type (pdf/docx/pptx/txt).
    3. Chunk the text.
    4. Generate embeddings for each chunk using Ollama all-minilm:l6-v2.
    5. Store each chunk + vector in DocumentChunk (pgvector).
    6. Mark Document.is_embedded = True.
    """

    # ----- Step 1: get file from storage -----
    django_file = doc.file  # FileField using MinIO via django-storages
    text = extract_text_from_fileobj(django_file, doc.mime_type or "")

    # If file had no readable text, stop
    if not text.strip():
        return 0

    # ----- Step 2: chunk the text -----
    chunks = chunk_text(text)

    # ----- Step 3: embed each chunk via Ollama -----
    vectors = embed_chunks(chunks)

    # ----- Step 4: save chunks + vectors to DB -----
    # Remove any old chunks for this document (re-embedding case)
    DocumentChunk.objects.filter(document=doc).delete()

    objs = []
    for idx, (chunk_text_value, vec) in enumerate(zip(chunks, vectors)):
        objs.append(
            DocumentChunk(
                document=doc,
                chunk_index=idx,
                text=chunk_text_value,
                embedding=vec,                  # pgvector.VectorField
                embedding_model=EMBEDDING_MODEL_NAME,
            )
        )

    # Bulk insert all chunks for speed
    DocumentChunk.objects.bulk_create(objs)

    # ----- Step 5: mark document as embedded -----
    doc.is_embedded = True
    doc.save(update_fields=["is_embedded", "updated_at"])

    # Return how many chunks we created (for debugging/UI)
    return len(objs)
