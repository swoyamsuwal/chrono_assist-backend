# ===============================================================
#  mail/views.py
#  All API views for one-on-one email and bulk campaign management
#
#  VIEW OVERVIEW:
#  One-on-One:
#   1. GenerateEmailView          → POST  AI-draft an email with LLaMA
#   2. SendEmailView              → POST  send a single email via SMTP
#
#  Campaign CRUD:
#   3. CampaignListCreateView     → GET/POST  list or create campaigns
#   4. CampaignDetailView         → GET/PATCH/DELETE  manage one campaign
#
#  Recipient Management:
#   5. CampaignRecipientsView     → GET/POST  list or add recipients
#   6. CampaignRecipientDetailView→ PATCH/DELETE  edit or remove one recipient
#
#  Bulk Send:
#   7. CampaignBulkSendView       → POST  send campaign to all recipients (async)
#
#  INTERNAL HELPERS:
#   _extract_name()   → auto-generates a display name from an email address
#   _get_campaign()   → fetches a campaign scoped to the current company group
# ===============================================================


# ---------------- Step 0: Imports ----------------
import threading  # Used to send bulk email in a background thread (non-blocking response)

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail, send_mass_mail  # Django's built-in email senders
from django.core.validators import validate_email        # Validates email format before saving

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authapp.utils import get_group_id  # Resolves company group_id for any user

from .llm_client import generate_email_draft  # LLaMA-powered email generator
from .models import CampaignRecipient, EmailCampaign
from .rbac_perms import (
    CanViewMail, CanSendMail,
    CanViewBulkMail, CanCreateBulkMail, CanEditBulkMail,
    CanDeleteBulkMail, CanSendBulkMail,
)
from .serializers import (
    BulkSendSerializer, CampaignRecipientSerializer,
    EmailCampaignSerializer, GenerateEmailSerializer, SendEmailSerializer,
)


# ================================================================
#  View 1: GenerateEmailView
#  POST /api/mail/generate/
#  Body: { "prompt": "...", "tone": "general_professional" }
#  Sends the prompt to LLaMA and returns a draft {subject, body}
#  Requires: IsAuthenticated + CanViewMail (mail:view RBAC check)
# ================================================================
class GenerateEmailView(APIView):
    permission_classes = [IsAuthenticated, CanViewMail]

    def post(self, request):
        # ---------------- Step 1: Validate Input ----------------
        serializer = GenerateEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # ---------------- Step 2: Generate Draft via LLaMA ----------------
        # generate_email_draft() invokes local LLaMA and returns {subject, body}
        draft = generate_email_draft(
            serializer.validated_data["prompt"],
            serializer.validated_data["tone"],
        )
        return Response(draft, status=status.HTTP_200_OK)


# ================================================================
#  View 2: SendEmailView
#  POST /api/mail/send/
#  Body: { "recipient": "...", "subject": "...", "body": "..." }
#  Sends a single email via Django's SMTP backend (Gmail)
#  Requires: IsAuthenticated + CanSendMail (mail:execute RBAC check)
# ================================================================
class SendEmailView(APIView):
    permission_classes = [IsAuthenticated, CanSendMail]

    def post(self, request):
        # ---------------- Step 1: Validate Input ----------------
        serializer = SendEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # ---------------- Step 2: Send via SMTP ----------------
        # send_mail() uses EMAIL_HOST_USER from settings as the sender
        # Returns 1 if sent successfully, 0 if it failed
        sent = send_mail(
            subject=serializer.validated_data["subject"],
            message=serializer.validated_data["body"],
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[serializer.validated_data["recipient"]],
            fail_silently=False,
        )
        return Response({"sent": bool(sent)}, status=status.HTTP_200_OK)


# ================================================================
#  Private Helper 1: _extract_name
#  Auto-generates a display name from an email address
#  Used when bulk-importing recipients so the "Dear {name}" greeting is personalized
#
#  Example: "john.doe@company.com" → "John"
#           "sarah_smith@gmail.com" → "Sarah"
# ================================================================
def _extract_name(email: str) -> str:
    local = email.split("@")[0]                    # "john.doe"
    first = local.replace(".", "_").split("_")[0]  # "john"
    return first.capitalize()              # "John"


# ================================================================
#  Private Helper 2: _get_campaign
#  Fetches a campaign by PK scoped to the current company's group_id
#  Returns the campaign object or None (caller handles the 404 response)
#  The group_id check prevents users from accessing other companies' campaigns
# ================================================================
def _get_campaign(pk: int, group_id: int):
    try:
        return EmailCampaign.objects.get(pk=pk, group_id=group_id)
    except EmailCampaign.DoesNotExist:
        return None


# ================================================================
#  View 3: CampaignListCreateView
#  GET  /api/mail/campaigns/  → list all campaigns for this company group
#  POST /api/mail/campaigns/  → create a new campaign
#
#  get_permissions() dynamically assigns RBAC based on HTTP method:
#   GET  → CanViewBulkMail   (bulk_mail:view)
#   POST → CanCreateBulkMail (bulk_mail:create)
# ================================================================
class CampaignListCreateView(APIView):

    def get_permissions(self):
        # Dynamic permission assignment based on method
        if self.request.method == "GET":
            return [IsAuthenticated(), CanViewBulkMail()]
        return [IsAuthenticated(), CanCreateBulkMail()]

    # ---------------- GET: List Campaigns ----------------
    def get(self, request):
        # Filter by group_id → user only sees their company's campaigns
        campaigns = EmailCampaign.objects.filter(
            group_id=get_group_id(request.user)
        ).order_by("-created_at")
        return Response(EmailCampaignSerializer(campaigns, many=True).data)

    # ---------------- POST: Create Campaign ----------------
    def post(self, request):
        name = request.data.get("name", "").strip()
        if not name:
            return Response({"error": "name is required"}, status=status.HTTP_400_BAD_REQUEST)

        # group_id links this campaign to the user's company
        # created_by tracks who created it (for future audit/ownership UI)
        campaign = EmailCampaign.objects.create(
            group_id=get_group_id(request.user),
            name=name,
            created_by=request.user,
        )
        return Response(
            EmailCampaignSerializer(campaign).data,
            status=status.HTTP_201_CREATED,
        )


# ================================================================
#  View 4: CampaignDetailView
#  GET    /api/mail/campaigns/<pk>/  → fetch full campaign + recipients
#  PATCH  /api/mail/campaigns/<pk>/  → update name, subject, or body
#  DELETE /api/mail/campaigns/<pk>/  → delete campaign + all recipients
#
#  get_permissions() assigns RBAC per method:
#   GET    → CanViewBulkMail   (bulk_mail:view)
#   PATCH  → CanEditBulkMail   (bulk_mail:update)
#   DELETE → CanDeleteBulkMail (bulk_mail:delete)
# ================================================================
class CampaignDetailView(APIView):

    def get_permissions(self):
        if self.request.method == "DELETE":
            return [IsAuthenticated(), CanDeleteBulkMail()]
        if self.request.method == "PATCH":
            return [IsAuthenticated(), CanEditBulkMail()]
        return [IsAuthenticated(), CanViewBulkMail()]

    # ---------------- GET: Fetch Campaign ----------------
    def get(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(EmailCampaignSerializer(obj).data)

    # ---------------- PATCH: Update Campaign ----------------
    # Only updates fields that are present in the request body (partial update)
    def patch(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        # Walrus operator (:=) assigns and checks in one step — only updates if non-empty
        if name := request.data.get("name", "").strip():
            obj.name = name
        if "subject" in request.data:
            obj.subject = request.data["subject"].strip()
        if "body" in request.data:
            obj.body = request.data["body"].strip()
        obj.save()
        return Response(EmailCampaignSerializer(obj).data)

    # ---------------- DELETE: Delete Campaign ----------------
    # Cascades to all CampaignRecipient rows automatically (model FK CASCADE)
    def delete(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ================================================================
#  View 5: CampaignRecipientsView
#  GET  /api/mail/campaigns/<pk>/recipients/  → list all recipients
#  POST /api/mail/campaigns/<pk>/recipients/  → add recipients
#
#  POST supports two input methods (can be combined in one request):
#   a) "emails": [...] → JSON array of email strings
#   b) "file": <upload> → CSV or plain text file, one email per line
#
#  get_permissions():
#   GET  → CanViewBulkMail  (bulk_mail:view)
#   POST → CanSendBulkMail  (bulk_mail:execute — adding recipients = preparing a send)
# ================================================================
class CampaignRecipientsView(APIView):

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated(), CanViewBulkMail()]
        return [IsAuthenticated(), CanSendBulkMail()]

    # ---------------- GET: List Recipients ----------------
    def get(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            CampaignRecipientSerializer(obj.recipients.all(), many=True).data
        )

    # ---------------- POST: Add Recipients ----------------
    def post(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        added, skipped = [], []

        # ---------------- Inner Helper: _add_one ----------------
        # Processes a single email string:
        #  1. Strip whitespace and lowercase
        #  2. Validate email format — invalid ones go to skipped[]
        #  3. get_or_create → inserts if new, skips if duplicate
        def _add_one(raw_email: str):
            email = raw_email.strip().lower()
            if not email:
                return
            try:
                validate_email(email)  # Raises ValidationError for bad format
            except ValidationError:
                skipped.append(email)
                return

            # Auto-generate name from email local part (e.g., "john.doe@" → "John")
            name = _extract_name(email)
            _, created = CampaignRecipient.objects.get_or_create(
                campaign=obj,
                email=email,
                defaults={"name": name},
            )
            # created=True → new row, added[]; created=False → duplicate, skipped[]
            (added if created else skipped).append(email)

        # ---------------- Process File Upload ----------------
        # Accepts CSV or plain text — reads first column as the email address
        # "line.split(',')" handles CSV where email is the first field
        uploaded_file = request.FILES.get("file")
        if uploaded_file:
            content = uploaded_file.read().decode("utf-8", errors="ignore")
            for line in content.splitlines():
                _add_one(line.split(",")[0].strip().strip('"'))

        # ---------------- Process JSON Array ----------------
        # Handles direct API calls with {"emails": ["a@b.com", "c@d.com"]}
        for email in request.data.get("emails", []):
            _add_one(str(email))

        return Response({"added": added, "skipped_duplicates": skipped})


# ================================================================
#  View 6: CampaignRecipientDetailView
#  PATCH  /api/mail/campaigns/<pk>/recipients/<rid>/  → update recipient name
#  DELETE /api/mail/campaigns/<pk>/recipients/<rid>/  → remove recipient
#
#  get_permissions():
#   PATCH  → CanEditBulkMail   (bulk_mail:update)
#   DELETE → CanDeleteBulkMail (bulk_mail:delete)
# ================================================================
class CampaignRecipientDetailView(APIView):

    def get_permissions(self):
        if self.request.method == "DELETE":
            return [IsAuthenticated(), CanDeleteBulkMail()]
        return [IsAuthenticated(), CanEditBulkMail()]

    # ---------------- Internal: _get_recipient ----------------
    # Two-step lookup: first get the campaign (group-scoped), then get the recipient
    # Returns (campaign, recipient) tuples — either can be None if not found
    def _get_recipient(self, pk, rid, group_id):
        obj = _get_campaign(pk, group_id)
        if not obj:
            return None, None
        try:
            # campaign=obj → ensures the recipient belongs to THIS campaign (not another)
            return obj, CampaignRecipient.objects.get(pk=rid, campaign=obj)
        except CampaignRecipient.DoesNotExist:
            return obj, None

    # ---------------- PATCH: Update Recipient Name ----------------
    def patch(self, request, pk, rid):
        _, recipient = self._get_recipient(pk, rid, get_group_id(request.user))
        if not recipient:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        # Only update if a non-empty name was provided
        if new_name := request.data.get("name", "").strip():
            recipient.name = new_name
            recipient.save()
        return Response(CampaignRecipientSerializer(recipient).data)

    # ---------------- DELETE: Remove Recipient ----------------
    def delete(self, request, pk, rid):
        _, recipient = self._get_recipient(pk, rid, get_group_id(request.user))
        if not recipient:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        recipient.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ================================================================
#  View 7: CampaignBulkSendView
#  POST /api/mail/campaigns/<pk>/send/
#  Sends the campaign's saved draft to ALL recipients in a background thread
#
#  Flow:
#   Step 1 → Verify campaign exists and belongs to this company group
#   Step 2 → Validate that a subject + body draft exists
#   Step 3 → Validate that the campaign has at least one recipient
#   Step 4 → Build a tuple of email messages (one per recipient, personalized)
#   Step 5 → Fire send_mass_mail() in a daemon thread → respond immediately
#  Requires: IsAuthenticated + CanSendBulkMail (bulk_mail:execute RBAC check)
# ================================================================
class CampaignBulkSendView(APIView):
    permission_classes = [IsAuthenticated, CanSendBulkMail]

    def post(self, request, pk):
        # ---------------- Step 1: Fetch Campaign ----------------
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        # ---------------- Step 2: Validate Draft Exists ----------------
        # Can't send without both subject and body
        if not obj.subject or not obj.body:
            return Response(
                {"error": "No email draft saved. Click 'Edit Draft' to write the subject and body first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------------- Step 3: Validate Recipients Exist ----------------
        recipients = list(obj.recipients.all())
        if not recipients:
            return Response(
                {"error": "No recipients in this campaign. Click 'People' to add emails first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------------- Step 4: Build Message Tuples ----------------
        # send_mass_mail() expects a tuple of (subject, body, from, [to]) tuples
        # Each recipient gets a personalized "Dear {name}" greeting
        messages = tuple(
            (
                obj.subject,
                f"Dear {r.name},\n\n{obj.body}",  # Personalized body per recipient
                settings.EMAIL_HOST_USER,           # Sender (from settings.py)
                [r.email],                          # Each email sent individually
            )
            for r in recipients
        )

        # ---------------- Step 5: Send in Background Thread ----------------
        # threading.Thread + daemon=True → background thread dies if the main process exits
        # The API returns {"queued": True} immediately without waiting for all emails to send
        # fail_silently=True → individual send failures don't crash the thread
        def _send_all():
            send_mass_mail(messages, fail_silently=True)

        threading.Thread(target=_send_all, daemon=True).start()

        return Response(
            {"queued": True, "total_recipients": len(recipients)},
            status=status.HTTP_200_OK,
        )