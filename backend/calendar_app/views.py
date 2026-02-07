import json
import os
from datetime import datetime, timezone, timedelta

from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request as GoogleRequest

from .models import GoogleCredentials
from .serializers import PromptSerializer

# SCOPES for full calendar read/write
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Helper: read stored credentials
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

# 1) Redirect to Google's OAuth2 consent screen
@api_view(["GET"])
def google_login(request):
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(client_config=client_config, scopes=SCOPES, redirect_uri=settings.GOOGLE_REDIRECT_URI)
    auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    return Response({"auth_url": auth_url})

# 2) Callback: exchange code and save credentials
@csrf_exempt
def google_callback(request):
    # This is called by Google with ?code=...
    code = request.GET.get("code")
    if not code:
        return HttpResponse("Missing code", status=400)

    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(client_config=client_config, scopes=SCOPES, redirect_uri=settings.GOOGLE_REDIRECT_URI)
    flow.fetch_token(code=code)
    creds = flow.credentials
    # Save credentials to DB
    # Remove old ones for dev clarity
    GoogleCredentials.objects.all().delete()
    save_credentials_from_flow(creds)

    # Redirect back to your frontend (if desired)
    # For dev, redirect to Next.js page
    return HttpResponseRedirect("http://localhost:3000/calendar?connected=1")

# Helper: build service
def build_calendar_service(creds):
    return build("calendar", "v3", credentials=creds, cache_discovery=False)

# GET events
@api_view(["GET"])
def list_events(request):
    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)
    service = build_calendar_service(creds)
    # list upcoming 250 events starting from now - 2 months to 1 year for demo
    now = datetime.utcnow().isoformat() + "Z"
    time_min = (datetime.utcnow() - timedelta(days=60)).isoformat() + "Z"
    events_result = service.events().list(calendarId="primary", timeMin=time_min, maxResults=250, singleEvents=True, orderBy="startTime").execute()
    items = events_result.get("items", [])
    return Response(items)

# POST create event
@api_view(["POST"])
def create_event(request):
    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)
    service = build_calendar_service(creds)
    payload = request.data
    # expected: {summary, description, start: {dateTime, timeZone}, end: {dateTime, timeZone}, ...}
    event = service.events().insert(calendarId="primary", body=payload).execute()
    return Response(event, status=201)

# PATCH update event
@api_view(["PATCH"])
def update_event(request, event_id):
    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)
    service = build_calendar_service(creds)
    payload = request.data
    event = service.events().patch(calendarId="primary", eventId=event_id, body=payload).execute()
    return Response(event)

# DELETE event
@api_view(["DELETE"])
def delete_event(request, event_id):
    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)
    service = build_calendar_service(creds)
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return Response({"status": "deleted"})

# -------------------------
# Simple AI prompt endpoint:
# Accepts natural-language prompt, attempts to detect action and executes it.
# We implement a robust fallback parser (regex + date parsing), and also
# provide a hook to call an external LLM (Ollama) if you want to parse more complex prompts.
# -------------------------
def parse_prompt_to_action(prompt_text):
    """
    Very small heuristic parser:
    - looks for verbs create/add/schedule -> create
    - looks for update/edit/modify/change -> update
    - looks for delete/remove/cancel -> delete
    - extracts quoted title or "title: ..." or first phrase as title
    - tries to parse datetime using dateutil.parser
    Returns: dict {action: "create"|"update"|"delete"|"list", data: {summary, description, start, end, event_id}}
    """
    import re
    from dateutil import parser as dateparser

    text = prompt_text.strip().lower()
    result = {"action": "list", "data": {}}

    # action
    if re.search(r"\b(create|add|schedule|make|set up)\b", text):
        result["action"] = "create"
    elif re.search(r"\b(update|edit|modify|change)\b", text):
        result["action"] = "update"
    elif re.search(r"\b(delete|remove|cancel)\b", text):
        result["action"] = "delete"
    elif re.search(r"\b(list|show|what are)\b", text):
        result["action"] = "list"

    # title: look for quotes or "title" or "called"
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

    # event id extraction if user said "event id ..."
    m = re.search(r"event id[:\s]*([A-Za-z0-9_\-]+)", prompt_text, flags=re.I)
    if m:
        result["data"]["event_id"] = m.group(1).strip()

    # datetime parsing: attempt to find expressions like "tomorrow at 3pm", "on Feb 10 at 14:00", etc.
    # We attempt to find sentences chunk with "on" or "at" and pass to dateutil
    datetime_candidates = []
    # naive capture: look for phrases with 'at', 'on', 'tomorrow', 'next', weekdays, date words
    possible_phrases = re.findall(r"(?:(?:on|at|for|from|starting|start|ending|end)\s+[A-Za-z0-9\:\,\sAPMapm\-]+)", prompt_text, flags=re.I)
    # also capture standalone words like "tomorrow", "today", "next monday", "next week"
    simple_phrases = re.findall(r"\b(today|tomorrow|tonight|next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week))\b", prompt_text, flags=re.I)

    for p in possible_phrases + simple_phrases:
        try:
            dt = dateparser.parse(p, fuzzy=True, default=datetime.now())
            if dt:
                datetime_candidates.append((p, dt))
        except Exception:
            pass

    # If found at least one datetime, use the first as start.
    if datetime_candidates:
        start_dt = datetime_candidates[0][1]
        # default duration 1 hour
        end_dt = start_dt + timedelta(hours=1)
        result["data"]["start"] = start_dt.isoformat()
        result["data"]["end"] = end_dt.isoformat()

    # if create and no title, try to derive a short summary
    if result["action"] == "create" and "summary" not in result["data"]:
        # first 6 words as summary
        words = prompt_text.split()
        result["data"]["summary"] = " ".join(words[:6]).strip()

    return result

@api_view(["POST"])
def ai_prompt_handler(request):
    """
    Accepts JSON: { "prompt": "create meeting tomorrow at 3pm with alice about demo" }
    Returns: {status, action, details, google_response (if any)}
    """
    serializer = PromptSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    prompt = serializer.validated_data["prompt"]

    # Optionally: call your Ollama / LangChain parser here (not required). We'll fallback to parser.
    # For now we attempt heuristic parse
    parsed = parse_prompt_to_action(prompt)
    action = parsed["action"]
    data = parsed["data"]

    creds = load_credentials()
    if not creds:
        return Response({"detail": "No credentials. Please connect Google Calendar."}, status=401)

    service = build_calendar_service(creds)

    # Execute the action
    try:
        if action == "list":
            events_result = service.events().list(calendarId="primary", maxResults=250, singleEvents=True, orderBy="startTime").execute()
            items = events_result.get("items", [])
            return Response({"status": "ok", "action": "list", "result": items})
        elif action == "create":
            body = {
                "summary": data.get("summary", "Untitled"),
                "description": data.get("description", ""),
            }
            # set start/end if present
            if "start" in data:
                body["start"] = {"dateTime": data["start"], "timeZone": "UTC"}
                body["end"] = {"dateTime": data.get("end", data["start"]), "timeZone": "UTC"}
            else:
                # default today + 1 hour
                now = datetime.utcnow().replace(tzinfo=timezone.utc)
                body["start"] = {"dateTime": now.isoformat()}
                body["end"] = {"dateTime": (now + timedelta(hours=1)).isoformat()}

            ev = service.events().insert(calendarId="primary", body=body).execute()
            return Response({"status": "created", "action": "create", "result": ev})
        elif action == "update":
            event_id = data.get("event_id")
            if not event_id:
                # try to find by title
                if "summary" in data:
                    q = data["summary"]
                    found = service.events().list(calendarId="primary", q=q, maxResults=10, singleEvents=True).execute()
                    items = found.get("items", [])
                    if not items:
                        return Response({"status": "not_found", "detail": f"No event matching '{q}'"})
                    # pick the first
                    event = items[0]
                    event_id = event["id"]
                else:
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
        elif action == "delete":
            # identify event to delete either by event_id or by summary
            event_id = data.get("event_id")
            if event_id:
                service.events().delete(calendarId="primary", eventId=event_id).execute()
                return Response({"status": "deleted", "action": "delete", "event_id": event_id})
            elif "summary" in data:
                q = data["summary"]
                found = service.events().list(calendarId="primary", q=q, maxResults=10, singleEvents=True).execute()
                items = found.get("items", [])
                if not items:
                    return Response({"status": "not_found", "detail": f"No event matching '{q}'"})
                # delete first match
                eid = items[0]["id"]
                service.events().delete(calendarId="primary", eventId=eid).execute()
                return Response({"status": "deleted", "action": "delete", "event_id": eid})
            else:
                return Response({"status": "error", "detail": "No event_id or summary provided to delete"}, status=400)
        else:
            return Response({"status": "error", "detail": "Unknown action parsed."}, status=400)
    except Exception as ex:
        print("AI prompt handler error:", ex)
        return Response({"status": "error", "detail": str(ex)}, status=500)
