# ===============================================================
#  calendar_app/urls.py
#  URL routing for Google Calendar integration and AI prompt endpoint
#  Mounted under /api/calendar/ in backend/urls.py
# ===============================================================


# ---------------- Step 0: Imports ----------------
from django.urls import path
from . import views


urlpatterns = [

    # ---------------- Step 1: Google OAuth2 Flow ----------------
    # GET  → generates the Google consent screen URL and returns it to Next.js
    #        Next.js redirects the user's browser to that URL
    path("google/login/", views.google_login, name="google_login"),

    # GET  → Google redirects here after the user grants consent
    #        Exchanges the auth code for credentials and saves them
    #        Then redirects the browser to Next.js (/calendar?connected=1)
    path("google/callback/", views.google_callback, name="google_callback"),

    # ---------------- Step 2: Calendar CRUD ----------------
    # GET  → lists all events from the primary calendar (±1 year range, up to 500)
    path("events/", views.list_events, name="list_events"),

    # POST → creates a new event using the full body sent by the client
    path("events/create/", views.create_event, name="create_event"),

    # PATCH → partially updates an event by its Google event ID
    path("events/<str:event_id>/", views.update_event, name="update_event"),

    # DELETE → removes an event by its Google event ID
    path("events/<str:event_id>/delete/", views.delete_event, name="delete_event"),

    # ---------------- Step 3: AI Natural Language Prompt ----------------
    # POST → accepts a plain-English prompt (e.g., "Cancel my 3pm meeting tomorrow")
    #        LLaMA parses it → action is dispatched to the correct Google Calendar API call
    path("ai-prompt/", views.ai_prompt_handler, name="ai_prompt"),
]