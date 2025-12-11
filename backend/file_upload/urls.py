from django.urls import path
from . import views

urlpatterns = [
    path("list_files/", views.list_files, name="list_files"),
    path("upload_file/", views.upload_file, name="upload_file"),
    path("delete_file/", views.delete_file, name="delete_file"),
    path("embed_file/", views.embed_file, name="embed_file"), 
    path("rag_chat/", views.rag_chat, name="rag_chat"),  # NEW
]
