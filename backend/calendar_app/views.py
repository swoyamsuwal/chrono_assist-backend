import json
from datetime import datetime, timezone, timedelta

from django.conf import settings
from django.core import signing
from django.http import HttpResponseRedirect
from django.contrib.auth import get_user_model

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request as GoogleRequest

from .models import GoogleCredentials
from .serializers import PromptSerializer
from .rbac_perms import CanConnectGoogleCalendar, CanSendCalendarPrompt


User = get_user_model()

# SCOPES for full calendar read/write
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Signed state settings (used to identify who started OAuth)
STATE_SALT = "calendar-oauth-state"
STATE_MAX_AGE_SECONDS = 10 * 60  # 10 minutes


# -----------------------------
# Helper: read stored credentials
# -----------------------------
def load_credentials():
    """
    Returns google.oauth2.credentials.Credentials or None
    """
    try:
        creds_obj = GoogleCredentials.objects.order_by("-updated_at").first()
        if not creds_obj or not creds_obj.credentials_json:
            return None

        creds_data = json.loads(creds_obj.credentials_json)
        creds = Credentials.from_authorized_user_info(creds_data, scopes=SCOPES)

        # If expired and refresh token present, refresh
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            # persist new token
            creds_obj.credentials_json = json.dumps(json.loads(creds.to_json()))
            creds_obj.save()

        return creds
    except Exception as e:
        print("load_credentials error:", e)
        return None


def save_credentials_from_flow(credentials):
    """
    credentials: google.oauth2.credentials.Credentials
    """
    creds_data = json.loads(credentials.to_json())
    obj = GoogleCredentials.objects.create(credentials_json=json.dumps(creds_data))
    return obj


def build_calendar_service(creds):
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


# -----------------------------------
# 1) Start OAuth (protected by RBAC)
# -----------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated, CanConnectGoogleCalendar])
def google_login(request):
    """
    Returns Google auth_url. Only authenticated + RBAC-approved users can start connect flow.
    """
    # Signed state includes who started the flow
    state = signing.dumps({"uid": request.user.id}, salt=STATE_SALT)

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
        redirect_uri=settings.GOOGLE_REDIRECT_URI,  # must be backend callback URL
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,  # important
    )

    return Response({"auth_url": auth_url}, status=status.HTTP_200_OK)


# ---------------------------------------------------------
# 2) OAuth callback (must be public, secured via signed state)
# ---------------------------------------------------------
@api_view(["GET"])
@permission_classes([AllowAny])
def google_callback(request):
    """
    Google redirects here with ?code=...&state=...
    Can't require IsAuthenticated because browser redirect won't include Bearer token.
    We verify signed state to know which user initiated the flow.
    """
    code = request.GET.get("code")
    state = request.GET.get("state")

    if not code:
        return Response({"detail": "Missing code"}, status=status.HTTP_400_BAD_REQUEST)
    if not state:
        return Response({"detail": "Missing state"}, status=status.HTTP_400_BAD_REQUEST)

    # Validate signed state and recover uid
    try:
        state_data = signing.loads(state, salt=STATE_SALT, max_age=STATE_MAX_AGE_SECONDS)
        uid = state_data["uid"]
    except signing.SignatureExpired:
        return Response({"detail": "State expired. Please connect again."}, status=status.HTTP_400_BAD_REQUEST)
    except signing.BadSignature:
        return Response({"detail": "Invalid state. Please connect again."}, status=status.HTTP_400_BAD_REQUEST)

    # (Optional sanity check) ensure user exists
    try:
        User.objects.get(id=uid)
    except User.DoesNotExist:
        return Response({"detail": "User not found"}, status=status.HTTP_400_BAD_REQUEST)

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
    flow.fetch_token(code=code)

    # Save credentials (your current model is global/shared)
    GoogleCredentials.objects.all().delete()
    save_credentials_from_flow(flow.credentials)

    # Redirect back to frontend
    return HttpResponseRedirect("http://localhost:3000/calendar?connected=1")


# -----------------------------
# Calendar CRUD (protected)
# -----------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated, CanConnectGoogleCalendar])
def list_events(request):
    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)

    service = build_calendar_service(creds)

    time_min = (datetime.utcnow() - timedelta(days=60)).isoformat() + "Z"
    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        maxResults=250,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    items = events_result.get("items", [])
    return Response(items, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanConnectGoogleCalendar])
def create_event(request):
    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)

    service = build_calendar_service(creds)
    payload = request.data
    event = service.events().insert(calendarId="primary", body=payload).execute()
    return Response(event, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, CanConnectGoogleCalendar])
def update_event(request, event_id):
    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)

    service = build_calendar_service(creds)
    payload = request.data
    event = service.events().patch(calendarId="primary", eventId=event_id, body=payload).execute()
    return Response(event, status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated, CanConnectGoogleCalendar])
def delete_event(request, event_id):
    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)

    service = build_calendar_service(creds)
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return Response({"status": "deleted"}, status=status.HTTP_200_OK)


# -----------------------------
# AI Prompt endpoint (protected)
# -----------------------------
def parse_prompt_to_action(prompt_text):
    import re
    from dateutil import parser as dateparser

    text = prompt_text.strip().lower()
    result = {"action": "list", "data": {}}

    if re.search(r"\b(create|add|schedule|make|set up)\b", text):
        result["action"] = "create"
    elif re.search(r"\b(update|edit|modify|change)\b", text):
        result["action"] = "update"
    elif re.search(r"\b(delete|remove|cancel)\b", text):
        result["action"] = "delete"
    elif re.search(r"\b(list|show|what are)\b", text):
        result["action"] = "list"

    title = None
    m = re.search(r"'([^']+)'|\"([^\"]+)\"", prompt_text)
    if m:
        title = m.group(1) or m.group(2)
    else:
        m = re.search(r"(?:called|title|named)\s+([A-Za-z0-9\s\-:]+)", prompt_text, flags=re.I)
        if m:
            title = m.group(1).strip()

    if title:
        result["data"]["summary"] = title

    m = re.search(r"event id[:\s]*([A-Za-z0-9_\-]+)", prompt_text, flags=re.I)
    if m:
        result["data"]["event_id"] = m.group(1).strip()

    datetime_candidates = []
    possible_phrases = re.findall(
        r"(?:(?:on|at|for|from|starting|start|ending|end)\s+[A-Za-z0-9\:\,\sAPMapm\-]+)",
        prompt_text,
        flags=re.I,
    )
    simple_phrases = re.findall(
        r"\b(today|tomorrow|tonight|next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week))\b",
        prompt_text,
        flags=re.I,
    )

    for p in possible_phrases + simple_phrases:
        try:
            dt = dateparser.parse(p, fuzzy=True, default=datetime.now())
            if dt:
                datetime_candidates.append(dt)
        except Exception:
            pass

    if datetime_candidates:
        start_dt = datetime_candidates[0]
        end_dt = start_dt + timedelta(hours=1)
        result["data"]["start"] = start_dt.isoformat()
        result["data"]["end"] = end_dt.isoformat()

    if result["action"] == "create" and "summary" not in result["data"]:
        words = prompt_text.split()
        result["data"]["summary"] = " ".join(words[:6]).strip()

    return result


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanSendCalendarPrompt])
def ai_prompt_handler(request):
    serializer = PromptSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    prompt = serializer.validated_data["prompt"]

    parsed = parse_prompt_to_action(prompt)
    action = parsed["action"]
    data = parsed["data"]

    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)

    service = build_calendar_service(creds)

    try:
        if action == "list":
            events_result = service.events().list(
                calendarId="primary",
                maxResults=250,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            return Response({"status": "ok", "action": "list", "result": events_result.get("items", [])})

        if action == "create":
            body = {"summary": data.get("summary", "Untitled"), "description": data.get("description", "")}
            if "start" in data:
                body["start"] = {"dateTime": data["start"], "timeZone": "UTC"}
                body["end"] = {"dateTime": data.get("end", data["start"]), "timeZone": "UTC"}
            else:
                now = datetime.utcnow().replace(tzinfo=timezone.utc)
                body["start"] = {"dateTime": now.isoformat()}
                body["end"] = {"dateTime": (now + timedelta(hours=1)).isoformat()}

            ev = service.events().insert(calendarId="primary", body=body).execute()
            return Response({"status": "created", "action": "create", "result": ev})

        if action == "update":
            event_id = data.get("event_id")
            if not event_id and "summary" in data:
                q = data["summary"]
                found = service.events().list(calendarId="primary", q=q, maxResults=10, singleEvents=True).execute()
                items = found.get("items", [])
                if not items:
                    return Response({"status": "not_found", "detail": f"No event matching '{q}'"})
                event_id = items[0]["id"]
            if not event_id:
                return Response({"status": "error", "detail": "No event_id or summary to identify event."}, status=400)

            update_body = {}
            if "summary" in data:
                update_body["summary"] = data["summary"]
            if "description" in data:
                update_body["description"] = data["description"]
            if "start" in data:
                update_body["start"] = {"dateTime": data["start"], "timeZone": "UTC"}
            if "end" in data:
                update_body["end"] = {"dateTime": data["end"], "timeZone": "UTC"}

            ev = service.events().patch(calendarId="primary", eventId=event_id, body=update_body).execute()
            return Response({"status": "updated", "action": "update", "result": ev})

        if action == "delete":
            event_id = data.get("event_id")
            if not event_id and "summary" in data:
                q = data["summary"]
                found = service.events().list(calendarId="primary", q=q, maxResults=10, singleEvents=True).execute()
                items = found.get("items", [])
                if not items:
                    return Response({"status": "not_found", "detail": f"No event matching '{q}'"})
                event_id = items[0]["id"]

            if not event_id:
                return Response({"status": "error", "detail": "No event_id or summary provided to delete"}, status=400)

            service.events().delete(calendarId="primary", eventId=event_id).execute()
            return Response({"status": "deleted", "action": "delete", "event_id": event_id})

        return Response({"status": "error", "detail": "Unknown action parsed."}, status=400)

    except Exception as ex:
        print("AI prompt handler error:", ex)
        return Response({"status": "error", "detail": str(ex)}, status=500)
