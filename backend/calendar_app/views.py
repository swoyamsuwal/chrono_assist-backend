# ===============================================================
#  calendar_app/views.py
#  All API views for Google Calendar integration + AI prompt handler
#
#  VIEW OVERVIEW:
#  1. google_login       → GET  start Google OAuth2 flow, return consent URL
#  2. google_callback    → GET  exchange auth code for tokens, save credentials
#  3. list_events        → GET  list all calendar events (±1 year, up to 500)
#  4. create_event       → POST create a new event directly
#  5. update_event       → PATCH partially update an existing event
#  6. delete_event       → DELETE remove an event
#  7. ai_prompt_handler  → POST parse natural language → dispatch calendar action
#
#  INTERNAL HELPERS:
#  - load_credentials()          → load + auto-refresh stored Google tokens
#  - save_credentials_from_flow()→ persist new tokens after OAuth callback
#  - build_calendar_service()    → create Google Calendar API client
#  - _find_event_id()            → search for an event by title text
# ===============================================================


# ---------------- Step 0: Imports & Config ----------------
import json
from datetime import datetime, timezone, timedelta

from django.conf import settings
from django.core import signing            # CSRF-safe state token for OAuth flow
from django.http import HttpResponseRedirect
from django.contrib.auth import get_user_model

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status

# Google OAuth2 + Calendar API libraries
from google_auth_oauthlib.flow import Flow             # Manages the OAuth2 authorization flow
from google.oauth2.credentials import Credentials       # Represents stored OAuth2 tokens
from googleapiclient.discovery import build             # Builds the Google Calendar API client
from google.auth.transport.requests import Request as GoogleRequest  # Used to refresh expired tokens

from .models import GoogleCredentials
from .serializers import PromptSerializer
from .rbac_perms import CanConnectGoogleCalendar, CanSendCalendarPrompt
from .llm import extract_command, DEFAULT_TZ  # LLaMA-powered prompt parser

User = get_user_model()

# ---------------- OAuth2 Scope ----------------
# calendar scope → full read/write access to the user's Google Calendar
# If you only need read: use "https://www.googleapis.com/auth/calendar.readonly"
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# ---------------- State Token Config ----------------
# STATE_SALT → namespaces the signed state so it can't be reused across features
# STATE_MAX_AGE_SECONDS → state token expires after 10 minutes (prevents stale OAuth redirects)
STATE_SALT = "calendar-oauth-state"
STATE_MAX_AGE_SECONDS = 10 * 60  # 10 minutes


# ================================================================
#  Helper 1: load_credentials
#  Loads the stored Google OAuth2 credentials from the DB
#  If the access token is expired, automatically refreshes it using the refresh_token
#  Returns a valid Credentials object, or None if no credentials exist
# ================================================================
def load_credentials():
    try:
        # Always load the most recently updated row (latest token)
        creds_obj = GoogleCredentials.objects.order_by("-updated_at").first()
        if not creds_obj or not creds_obj.credentials_json:
            return None  # No credentials stored yet → user hasn't connected Google Calendar

        # Deserialize the JSON blob back into a Google Credentials object
        creds_data = json.loads(creds_obj.credentials_json)
        creds = Credentials.from_authorized_user_info(creds_data, scopes=SCOPES)

        # ---------------- Auto-Refresh Expired Tokens ----------------
        # Access tokens expire after ~1 hour. The refresh_token lets us get a new one silently.
        # GoogleRequest() makes the actual HTTP call to Google's token endpoint
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            # Persist the refreshed token back to DB so the next call doesn't re-refresh
            creds_obj.credentials_json = json.dumps(json.loads(creds.to_json()))
            creds_obj.save()

        return creds

    except Exception as e:
        print("load_credentials error:", e)
        return None  # Never crash the caller — return None and let the view handle it


# ================================================================
#  Helper 2: save_credentials_from_flow
#  Called immediately after the OAuth callback exchanges the auth code for tokens
#  Serializes the credentials to JSON and saves a new DB row
# ================================================================
def save_credentials_from_flow(credentials):
    # credentials.to_json() → full token JSON including refresh_token, client_id, etc.
    creds_data = json.loads(credentials.to_json())
    obj = GoogleCredentials.objects.create(credentials_json=json.dumps(creds_data))
    return obj


# ================================================================
#  Helper 3: build_calendar_service
#  Creates the Google Calendar API v3 client using the loaded credentials
#  cache_discovery=False → avoids file-system caching of the API discovery doc
#                          (prevents stale cache issues in long-running processes)
# ================================================================
def build_calendar_service(creds):
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


# ================================================================
#  View 1: google_login
#  GET /google/login/
#  Starts the Google OAuth2 flow
#
#  Flow:
#   Step 1 → Sign a state token containing the user's ID (prevents CSRF)
#   Step 2 → Build the OAuth2 Flow with Google's endpoints and our scopes
#   Step 3 → Generate the Google consent screen URL
#   Step 4 → Return the URL to Next.js (frontend redirects the user there)
#  Requires: IsAuthenticated + CanConnectGoogleCalendar (calendar:view RBAC check)
# ================================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated, CanConnectGoogleCalendar])
def google_login(request):
    # ---------------- Step 1: Generate CSRF-Safe State Token ----------------
    # signing.dumps() creates a tamper-proof signed string containing the user ID
    # Google will echo this state back in the callback — we verify it there
    state = signing.dumps({"uid": request.user.id}, salt=STATE_SALT)

    # ---------------- Step 2: Build OAuth2 Flow Config ----------------
    # We pass credentials inline (not via a file) to keep everything in settings
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,  # Must match Google Cloud Console registration
    )

    # ---------------- Step 3: Generate Consent URL ----------------
    # access_type="offline"           → requests a refresh_token so we can refresh without re-login
    # include_granted_scopes="true"   → preserves any previously granted scopes
    # prompt="consent"                → forces the consent screen every time (ensures refresh_token is returned)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )

    # ---------------- Step 4: Return URL to Next.js ----------------
    # Next.js will do: window.location.href = data.auth_url
    return Response({"auth_url": auth_url}, status=status.HTTP_200_OK)


# ================================================================
#  View 2: google_callback
#  GET /google/callback/
#  Google redirects here after the user grants (or denies) consent
#
#  Flow:
#   Step 1 → Extract code and state from query params
#   Step 2 → Verify the state token (tamper + expiry check)
#   Step 3 → Verify the user in state still exists in DB
#   Step 4 → Exchange auth code for OAuth2 tokens
#   Step 5 → Clear old credentials and save the new ones
#   Step 6 → Redirect browser back to Next.js with ?connected=1
#  AllowAny → Google sends the redirect without our session cookie
# ================================================================
@api_view(["GET"])
@permission_classes([AllowAny])
def google_callback(request):
    # ---------------- Step 1: Extract OAuth Params ----------------
    code = request.GET.get("code")    # One-time auth code from Google
    state = request.GET.get("state")  # The signed state we sent in google_login

    if not code:
        return Response({"detail": "Missing code"}, status=status.HTTP_400_BAD_REQUEST)
    if not state:
        return Response({"detail": "Missing state"}, status=status.HTTP_400_BAD_REQUEST)

    # ---------------- Step 2: Verify State Token ----------------
    # signing.loads() checks the signature AND the max_age
    # SignatureExpired → user took > 10 minutes to grant consent
    # BadSignature     → state was tampered with (CSRF attempt)
    try:
        state_data = signing.loads(state, salt=STATE_SALT, max_age=STATE_MAX_AGE_SECONDS)
        uid = state_data["uid"]
    except signing.SignatureExpired:
        return Response({"detail": "State expired. Please connect again."}, status=status.HTTP_400_BAD_REQUEST)
    except signing.BadSignature:
        return Response({"detail": "Invalid state. Please connect again."}, status=status.HTTP_400_BAD_REQUEST)

    # ---------------- Step 3: Verify User Still Exists ----------------
    try:
        User.objects.get(id=uid)
    except User.DoesNotExist:
        return Response({"detail": "User not found"}, status=status.HTTP_400_BAD_REQUEST)

    # ---------------- Step 4: Exchange Auth Code for Tokens ----------------
    # Rebuild the same Flow object used in google_login
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )
    # fetch_token() makes a POST to Google's token_uri to exchange code → tokens
    flow.fetch_token(code=code)

    # ---------------- Step 5: Replace Old Credentials ----------------
    # Delete all existing rows → system only ever keeps one active credential set
    GoogleCredentials.objects.all().delete()
    save_credentials_from_flow(flow.credentials)

    # ---------------- Step 6: Redirect to Next.js ----------------
    # ?connected=1 → Next.js can show a "Calendar connected!" success message
    return HttpResponseRedirect("http://localhost:3000/calendar?connected=1")


# ================================================================
#  View 3: list_events
#  GET /events/
#  Returns all events from the primary Google Calendar
#  Range: ±1 year from now, up to 500 events
#  Requires: IsAuthenticated + CanConnectGoogleCalendar (calendar:view)
# ================================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated, CanConnectGoogleCalendar])
def list_events(request):
    # ---------------- Step 1: Load Credentials ----------------
    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)

    service = build_calendar_service(creds)

    # ---------------- Step 2: Define Time Range ----------------
    # "Z" suffix → UTC time, required by the Google Calendar API
    time_min = (datetime.utcnow() - timedelta(days=365)).isoformat() + "Z"  # 1 year ago
    time_max = (datetime.utcnow() + timedelta(days=365)).isoformat() + "Z"  # 1 year ahead

    # ---------------- Step 3: Fetch Events ----------------
    # singleEvents=True → expands recurring events into individual instances
    # orderBy="startTime" → chronological order (required when singleEvents=True)
    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        maxResults=500,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    items = events_result.get("items", [])
    return Response(items, status=status.HTTP_200_OK)


# ================================================================
#  View 4: create_event
#  POST /events/create/
#  Creates a new Google Calendar event using the full body from the client
#  The client must send the complete event payload (summary, start, end, etc.)
#  Requires: IsAuthenticated + CanConnectGoogleCalendar (calendar:view)
# ================================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated, CanConnectGoogleCalendar])
def create_event(request):
    # ---------------- Step 1: Load Credentials ----------------
    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)

    # ---------------- Step 2: Insert Event ----------------
    # request.data is passed directly as the event body to Google Calendar API
    # Google returns the created event object including the assigned event ID
    service = build_calendar_service(creds)
    payload = request.data
    event = service.events().insert(calendarId="primary", body=payload).execute()
    return Response(event, status=status.HTTP_201_CREATED)


# ================================================================
#  View 5: update_event
#  PATCH /events/<event_id>/
#  Partially updates an existing event by its Google Calendar event ID
#  Only the fields sent in the body are changed (patch, not full replace)
#  Requires: IsAuthenticated + CanConnectGoogleCalendar (calendar:view)
# ================================================================
@api_view(["PATCH"])
@permission_classes([IsAuthenticated, CanConnectGoogleCalendar])
def update_event(request, event_id):
    # ---------------- Step 1: Load Credentials ----------------
    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)

    # ---------------- Step 2: Patch Event ----------------
    # events().patch() sends only the changed fields (PATCH semantics)
    # Unlike events().update() which requires the full event body (PUT semantics)
    service = build_calendar_service(creds)
    payload = request.data
    event = service.events().patch(calendarId="primary", eventId=event_id, body=payload).execute()
    return Response(event, status=status.HTTP_200_OK)


# ================================================================
#  View 6: delete_event
#  DELETE /events/<event_id>/delete/
#  Permanently removes an event from Google Calendar
#  Requires: IsAuthenticated + CanConnectGoogleCalendar (calendar:view)
# ================================================================
@api_view(["DELETE"])
@permission_classes([IsAuthenticated, CanConnectGoogleCalendar])
def delete_event(request, event_id):
    # ---------------- Step 1: Load Credentials ----------------
    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)

    # ---------------- Step 2: Delete Event ----------------
    # Google's delete() returns an empty response on success (HTTP 204)
    service = build_calendar_service(creds)
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return Response({"status": "deleted"}, status=status.HTTP_200_OK)


# ================================================================
#  Internal Helper: _find_event_id
#  Searches Google Calendar for an event by text query
#  Used by ai_prompt_handler when the user describes an event by title
#  (e.g., "delete my dentist appointment") instead of providing an event ID
#
#  Returns the ID of the first matching event, or None if not found
# ================================================================
def _find_event_id(service, query: str) -> str | None:
    if not query:
        return None

    # q= → full-text search across event titles, descriptions, and locations
    # Returns up to 10 results — we take the first (most recent/relevant) match
    found = service.events().list(
        calendarId="primary",
        q=query,
        maxResults=10,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    items = found.get("items", [])
    if not items:
        return None
    return items[0].get("id")  # Return the Google event ID of the best match


# ================================================================
#  View 7: ai_prompt_handler
#  POST /ai-prompt/
#  Body: { "prompt": "Schedule a team meeting tomorrow at 3pm" }
#  Parses a natural language prompt using LLaMA → dispatches the correct
#  Google Calendar API action (list / create / update / delete)
#
#  Flow:
#   Step 1 → Validate prompt via PromptSerializer
#   Step 2 → Load Google credentials
#   Step 3 → extract_command() → LLaMA parses prompt → CalendarCommand
#   Step 4 → Dispatch to the correct Google Calendar API call based on cmd.action
#  Requires: IsAuthenticated + CanSendCalendarPrompt (calendar:execute RBAC check)
# ================================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated, CanSendCalendarPrompt])
def ai_prompt_handler(request):
    # ---------------- Step 1: Validate Input ----------------
    serializer = PromptSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    prompt = serializer.validated_data["prompt"]

    # ---------------- Step 2: Load Credentials ----------------
    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)

    service = build_calendar_service(creds)

    try:
        # ---------------- Step 3: Parse Prompt with LLaMA ----------------
        # extract_command() → sends prompt to local LLaMA 3.2 → returns CalendarCommand
        cmd = extract_command(prompt)

        # ============================================================
        #  Step 4: Dispatch Based on cmd.action
        # ============================================================

        # ---------------- Action: LIST ----------------
        # Returns all upcoming events — no fields from cmd needed
        if cmd.action == "list":
            events_result = service.events().list(
                calendarId="primary",
                maxResults=250,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            return Response(
                {"status": "ok", "action": "list", "result": events_result.get("items", [])},
                status=status.HTTP_200_OK,
            )

        # ---------------- Action: CREATE ----------------
        # Requires at minimum: summary (title) and start_iso (date/time)
        # LLaMA fills in defaults: end = start + 1hr, time = 10am if date only
        if cmd.action == "create":
            if not cmd.summary:
                return Response({"detail": "Could not determine event title."}, status=400)
            if not cmd.start_iso:
                return Response({"detail": "Could not determine event date/time."}, status=400)

            body = {
                "summary": cmd.summary,
                "description": cmd.description or "",
                "location": cmd.location or "",
                "start": {"dateTime": cmd.start_iso, "timeZone": cmd.timeZone or DEFAULT_TZ},
                # end_iso is always set by extract_command() (default: start + 1hr)
                "end": {"dateTime": cmd.end_iso or cmd.start_iso, "timeZone": cmd.timeZone or DEFAULT_TZ},
            }

            ev = service.events().insert(calendarId="primary", body=body).execute()
            return Response(
                {"status": "created", "action": "create", "result": ev},
                status=status.HTTP_200_OK,
            )

        # ---------------- Action: UPDATE ----------------
        # event_id priority: LLaMA-provided ID → search by title/query
        # Only fields present in cmd are included in the PATCH body
        if cmd.action == "update":
            event_id = cmd.event_id or _find_event_id(service, cmd.query or cmd.summary or "")
            if not event_id:
                return Response(
                    {"detail": "Could not find which event to update. Provide event id or a clearer title."},
                    status=400
                )

            # Build a sparse update body — only include fields that LLaMA populated
            update_body = {}
            if cmd.summary:
                update_body["summary"] = cmd.summary
            if cmd.description is not None:
                update_body["description"] = cmd.description
            if cmd.location is not None:
                update_body["location"] = cmd.location
            if cmd.start_iso:
                update_body["start"] = {"dateTime": cmd.start_iso, "timeZone": cmd.timeZone or DEFAULT_TZ}
            if cmd.end_iso:
                update_body["end"] = {"dateTime": cmd.end_iso, "timeZone": cmd.timeZone or DEFAULT_TZ}

            if not update_body:
                return Response({"detail": "No update fields provided."}, status=400)

            ev = service.events().patch(calendarId="primary", eventId=event_id, body=update_body).execute()
            return Response(
                {"status": "updated", "action": "update", "result": ev},
                status=status.HTTP_200_OK,
            )

        # ---------------- Action: DELETE ----------------
        # event_id priority: LLaMA-provided ID → search by title/query
        if cmd.action == "delete":
            event_id = cmd.event_id or _find_event_id(service, cmd.query or cmd.summary or "")
            if not event_id:
                return Response(
                    {"detail": "Could not find which event to delete. Provide event id or a clearer title."},
                    status=400
                )

            service.events().delete(calendarId="primary", eventId=event_id).execute()
            return Response(
                {"status": "deleted", "action": "delete", "event_id": event_id},
                status=status.HTTP_200_OK,
            )

        return Response({"detail": "Unknown action."}, status=400)

    # ---------------- Error Handling ----------------
    except json.JSONDecodeError:
        # LLaMA returned something that isn't valid JSON (markdown, explanation text, etc.)
        return Response(
            {"detail": "LLM did not return valid JSON. Try rephrasing your prompt."},
            status=400,
        )
    except Exception as ex:
        print("AI prompt handler error:", ex)
        return Response({"detail": str(ex)}, status=500)