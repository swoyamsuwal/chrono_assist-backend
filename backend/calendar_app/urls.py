from django.urls import path
from . import views

urlpatterns = [
    path("google/login/", views.google_login, name="google_login"),
    path("google/callback/", views.google_callback, name="google_callback"),
    path("events/", views.list_events, name="list_events"),
    path("events/create/", views.create_event, name="create_event"),
    path("events/<str:event_id>/", views.update_event, name="update_event"),  # patch
    path("events/<str:event_id>/delete/", views.delete_event, name="delete_event"),
    path("ai-prompt/", views.ai_prompt_handler, name="ai_prompt"),
]
