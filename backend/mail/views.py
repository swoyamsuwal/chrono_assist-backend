import threading

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail, send_mass_mail
from django.core.validators import validate_email

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authapp.utils import get_group_id

from .llm_client import generate_email_draft
from .models import CampaignRecipient, EmailCampaign
from .rbac_perms import CanSendMail, CanViewMail
from .serializers import (
    BulkSendSerializer,
    CampaignRecipientSerializer,
    EmailCampaignSerializer,
    GenerateEmailSerializer,
    SendEmailSerializer,
)


# ─────────────────────────────────────────────────────────────────────────────
# Existing views — unchanged
# ─────────────────────────────────────────────────────────────────────────────

class GenerateEmailView(APIView):
    permission_classes = [IsAuthenticated, CanViewMail]

    def post(self, request):
        serializer = GenerateEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        draft = generate_email_draft(
            serializer.validated_data["prompt"],
            serializer.validated_data["tone"],
        )
        return Response(draft, status=status.HTTP_200_OK)


class SendEmailView(APIView):
    permission_classes = [IsAuthenticated, CanSendMail]

    def post(self, request):
        serializer = SendEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sent = send_mail(
            subject=serializer.validated_data["subject"],
            message=serializer.validated_data["body"],
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[serializer.validated_data["recipient"]],
            fail_silently=False,
        )
        return Response({"sent": bool(sent)}, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_name(email: str) -> str:
    """
    ram@gmail.com      → 'Ram'
    john.doe@work.com  → 'John'
    john_doe@work.com  → 'John'
    """
    local = email.split("@")[0]
    first = local.replace(".", "_").split("_")[0]
    return first.capitalize()


def _get_campaign(pk: int, group_id: int):
    """
    Fetch a campaign by PK scoped to the user's group.
    Returns None if not found — callers must handle the 404.
    """
    try:
        return EmailCampaign.objects.get(pk=pk, group_id=group_id)
    except EmailCampaign.DoesNotExist:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Campaign CRUD
# ─────────────────────────────────────────────────────────────────────────────

class CampaignListCreateView(APIView):
    """
    GET  /api/mail/campaigns/       → list all campaigns for the current group
    POST /api/mail/campaigns/       → create a new campaign (name only)
    """
    permission_classes = [IsAuthenticated, CanViewMail]

    def get(self, request):
        campaigns = EmailCampaign.objects.filter(
            group_id=get_group_id(request.user)
        ).order_by("-created_at")
        return Response(EmailCampaignSerializer(campaigns, many=True).data)

    def post(self, request):
        name = request.data.get("name", "").strip()
        if not name:
            return Response({"error": "name is required"}, status=status.HTTP_400_BAD_REQUEST)

        campaign = EmailCampaign.objects.create(
            group_id=get_group_id(request.user),
            name=name,
            created_by=request.user,
        )
        return Response(
            EmailCampaignSerializer(campaign).data,
            status=status.HTTP_201_CREATED,
        )


class CampaignDetailView(APIView):
    """
    GET    /api/mail/campaigns/<pk>/  → fetch one campaign (with recipients)
    PATCH  /api/mail/campaigns/<pk>/  → update name, subject, body (any combo)
    DELETE /api/mail/campaigns/<pk>/  → delete campaign + all its recipients
    """
    permission_classes = [IsAuthenticated, CanViewMail]

    def get(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(EmailCampaignSerializer(obj).data)

    def patch(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        # Update only the fields that were actually sent in the request
        if name := request.data.get("name", "").strip():
            obj.name = name
        if "subject" in request.data:
            obj.subject = request.data["subject"].strip()
        if "body" in request.data:
            obj.body = request.data["body"].strip()

        obj.save()
        return Response(EmailCampaignSerializer(obj).data)

    def delete(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────────────────────────────────────
# Recipient management
# ─────────────────────────────────────────────────────────────────────────────

class CampaignRecipientsView(APIView):
    """
    GET  /api/mail/campaigns/<pk>/recipients/
        → list all recipients for this campaign

    POST /api/mail/campaigns/<pk>/recipients/
        → add recipients via:
           a) JSON body: { "emails": ["a@b.com", "c@d.com"] }
           b) File upload: multipart field "file" (CSV or TXT, one email per line)
           Duplicate emails are silently skipped (unique_together enforced at DB level).
    """
    permission_classes = [IsAuthenticated, CanSendMail]

    def get(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = CampaignRecipientSerializer(obj.recipients.all(), many=True)
        return Response(serializer.data)

    def post(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        added, skipped = [], []

        def _add_one(raw_email: str):
            email = raw_email.strip().lower()
            if not email:
                return
            try:
                validate_email(email)
            except ValidationError:
                skipped.append(email)
                return

            name = _extract_name(email)
            _, created = CampaignRecipient.objects.get_or_create(
                campaign=obj,
                email=email,
                defaults={"name": name},
            )
            if created:
                added.append(email)
            else:
                skipped.append(email)

        # Option A — file upload (CSV or TXT)
        uploaded_file = request.FILES.get("file")
        if uploaded_file:
            content = uploaded_file.read().decode("utf-8", errors="ignore")
            for line in content.splitlines():
                # Handle CSV: take only the first column if commas present
                email_candidate = line.split(",")[0].strip().strip('"')
                _add_one(email_candidate)

        # Option B — JSON list
        for email in request.data.get("emails", []):
            _add_one(str(email))

        return Response({
            "added":              added,
            "skipped_duplicates": skipped,
        })


class CampaignRecipientDetailView(APIView):
    """
    PATCH  /api/mail/campaigns/<pk>/recipients/<rid>/  → edit recipient's display name
    DELETE /api/mail/campaigns/<pk>/recipients/<rid>/  → remove recipient from campaign
    """
    permission_classes = [IsAuthenticated, CanSendMail]

    def _get_recipient(self, pk: int, rid: int, group_id: int):
        """Returns (campaign, recipient) or (None, None) if either not found."""
        obj = _get_campaign(pk, group_id)
        if not obj:
            return None, None
        try:
            return obj, CampaignRecipient.objects.get(pk=rid, campaign=obj)
        except CampaignRecipient.DoesNotExist:
            return obj, None

    def patch(self, request, pk, rid):
        _, recipient = self._get_recipient(pk, rid, get_group_id(request.user))
        if not recipient:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        new_name = request.data.get("name", "").strip()
        if new_name:
            recipient.name = new_name
            recipient.save()

        return Response(CampaignRecipientSerializer(recipient).data)

    def delete(self, request, pk, rid):
        _, recipient = self._get_recipient(pk, rid, get_group_id(request.user))
        if not recipient:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        recipient.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────────────────────────────────────
# Bulk send
# ─────────────────────────────────────────────────────────────────────────────

class CampaignBulkSendView(APIView):
    """
    POST /api/mail/campaigns/<pk>/send/

    Sends the campaign's stored draft to all recipients.
    Fails fast (400) if:
      - No subject/body draft has been saved yet
      - The campaign has zero recipients

    Emails are sent in a background thread using send_mass_mail
    (one SMTP connection for all messages) so the API responds instantly.
    Each email is personalised: "Dear {name}," prepended to the body.
    """
    permission_classes = [IsAuthenticated, CanSendMail]

    def post(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        # Guard 1 — draft must exist
        if not obj.subject or not obj.body:
            return Response(
                {"error": "No email draft saved. Click 'Edit Draft' to write the subject and body first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Guard 2 — must have recipients
        recipients = list(obj.recipients.all())
        if not recipients:
            return Response(
                {"error": "No recipients in this campaign. Click 'People' to add emails first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build one personalised message tuple per recipient
        # send_mass_mail format: (subject, message, from_email, [recipient_list])
        messages = tuple(
            (
                obj.subject,
                f"Dear {r.name},\n\n{obj.body}",
                settings.EMAIL_HOST_USER,
                [r.email],
            )
            for r in recipients
        )

        # Fire and forget — background thread, no Celery needed
        def _send_all():
            send_mass_mail(messages, fail_silently=True)

        threading.Thread(target=_send_all, daemon=True).start()

        return Response(
            {
                "queued":            True,
                "total_recipients":  len(recipients),
            },
            status=status.HTTP_200_OK,
        )
