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
from .llm import extract_command, DEFAULT_TZ

User = get_user_model()

SCOPES = ["https://www.googleapis.com/auth/calendar"]

STATE_SALT = "calendar-oauth-state"
STATE_MAX_AGE_SECONDS = 10 * 60  # 10 minutes


def load_credentials():
    try:
        creds_obj = GoogleCredentials.objects.order_by("-updated_at").first()
        if not creds_obj or not creds_obj.credentials_json:
            return None

        creds_data = json.loads(creds_obj.credentials_json)
        creds = Credentials.from_authorized_user_info(creds_data, scopes=SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            creds_obj.credentials_json = json.dumps(json.loads(creds.to_json()))
            creds_obj.save()

        return creds
    except Exception as e:
        print("load_credentials error:", e)
        return None


def save_credentials_from_flow(credentials):
    creds_data = json.loads(credentials.to_json())
    obj = GoogleCredentials.objects.create(credentials_json=json.dumps(creds_data))
    return obj


def build_calendar_service(creds):
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


@api_view(["GET"])
@permission_classes([IsAuthenticated, CanConnectGoogleCalendar])
def google_login(request):
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
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )

    return Response({"auth_url": auth_url}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def google_callback(request):
    code = request.GET.get("code")
    state = request.GET.get("state")

    if not code:
        return Response({"detail": "Missing code"}, status=status.HTTP_400_BAD_REQUEST)
    if not state:
        return Response({"detail": "Missing state"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        state_data = signing.loads(state, salt=STATE_SALT, max_age=STATE_MAX_AGE_SECONDS)
        uid = state_data["uid"]
    except signing.SignatureExpired:
        return Response({"detail": "State expired. Please connect again."}, status=status.HTTP_400_BAD_REQUEST)
    except signing.BadSignature:
        return Response({"detail": "Invalid state. Please connect again."}, status=status.HTTP_400_BAD_REQUEST)

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

    GoogleCredentials.objects.all().delete()
    save_credentials_from_flow(flow.credentials)

    return HttpResponseRedirect("http://localhost:3000/calendar?connected=1")


@api_view(["GET"])
@permission_classes([IsAuthenticated, CanConnectGoogleCalendar])
def list_events(request):
    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)

    service = build_calendar_service(creds)

    # Fetch a wide range: 1 year back and 1 year forward
    time_min = (datetime.utcnow() - timedelta(days=365)).isoformat() + "Z"
    time_max = (datetime.utcnow() + timedelta(days=365)).isoformat() + "Z"

    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        maxResults=500,        # increase from 250
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


def _find_event_id(service, query: str) -> str | None:
    if not query:
        return None
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
    return items[0].get("id")


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanSendCalendarPrompt])
def ai_prompt_handler(request):
    serializer = PromptSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    prompt = serializer.validated_data["prompt"]

    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)

    service = build_calendar_service(creds)

    try:
        cmd = extract_command(prompt)

        # LIST
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

        # CREATE
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
                "end": {"dateTime": cmd.end_iso or cmd.start_iso, "timeZone": cmd.timeZone or DEFAULT_TZ},
            }

            ev = service.events().insert(calendarId="primary", body=body).execute()
            return Response(
                {"status": "created", "action": "create", "result": ev},
                status=status.HTTP_200_OK,
            )

        # UPDATE
        if cmd.action == "update":
            event_id = cmd.event_id or _find_event_id(service, cmd.query or cmd.summary or "")
            if not event_id:
                return Response({"detail": "Could not find which event to update. Provide event id or a clearer title."}, status=400)

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

        # DELETE
        if cmd.action == "delete":
            event_id = cmd.event_id or _find_event_id(service, cmd.query or cmd.summary or "")
            if not event_id:
                return Response({"detail": "Could not find which event to delete. Provide event id or a clearer title."}, status=400)

            service.events().delete(calendarId="primary", eventId=event_id).execute()
            return Response(
                {"status": "deleted", "action": "delete", "event_id": event_id},
                status=status.HTTP_200_OK,
            )

        return Response({"detail": "Unknown action."}, status=400)

    except json.JSONDecodeError:
        return Response(
            {"detail": "LLM did not return valid JSON. Try rephrasing your prompt."},
            status=400,
        )
    except Exception as ex:
        print("AI prompt handler error:", ex)
        return Response({"detail": str(ex)}, status=500)
