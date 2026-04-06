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
from .rbac_perms import (
    CanViewMail,
    CanSendMail,
    CanViewBulkMail,
    CanCreateBulkMail,
    CanEditBulkMail,
    CanDeleteBulkMail,
    CanSendBulkMail,
)
from .serializers import (
    BulkSendSerializer,
    CampaignRecipientSerializer,
    EmailCampaignSerializer,
    GenerateEmailSerializer,
    SendEmailSerializer,
)


# ─────────────────────────────────────────────────────────────────────────────
# One-on-one Mail views
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
    local = email.split("@")[0]
    first = local.replace(".", "_").split("_")[0]
    return first.capitalize()


def _get_campaign(pk: int, group_id: int):
    try:
        return EmailCampaign.objects.get(pk=pk, group_id=group_id)
    except EmailCampaign.DoesNotExist:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Campaign CRUD
# ─────────────────────────────────────────────────────────────────────────────

class CampaignListCreateView(APIView):
    """
    GET  /api/mail/campaigns/   → list campaigns
    POST /api/mail/campaigns/   → create campaign
    """
    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated(), CanViewBulkMail()]
        return [IsAuthenticated(), CanCreateBulkMail()]

    def get(self, request):
        campaigns = EmailCampaign.objects.filter(
            group_id=get_group_id(request.user)
        ).order_by("-created_at")
        return Response(EmailCampaignSerializer(campaigns, many=True).data)

    def post(self, request):
        name = request.data.get("name", "").strip()
        if not name:
            return Response(
                {"error": "name is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
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
    GET    /api/mail/campaigns/<pk>/   → fetch one campaign
    PATCH  /api/mail/campaigns/<pk>/   → update name/subject/body
    DELETE /api/mail/campaigns/<pk>/   → delete campaign
    """
    def get_permissions(self):
        if self.request.method == "DELETE":
            return [IsAuthenticated(), CanDeleteBulkMail()]
        if self.request.method == "PATCH":
            return [IsAuthenticated(), CanEditBulkMail()]
        return [IsAuthenticated(), CanViewBulkMail()]   # GET

    def get(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(EmailCampaignSerializer(obj).data)

    def patch(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
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
    GET  /api/mail/campaigns/<pk>/recipients/   → list recipients
    POST /api/mail/campaigns/<pk>/recipients/   → add recipients (JSON or file)
    """
    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated(), CanViewBulkMail()]
        return [IsAuthenticated(), CanSendBulkMail()]

    def get(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            CampaignRecipientSerializer(obj.recipients.all(), many=True).data
        )

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
            (added if created else skipped).append(email)

        uploaded_file = request.FILES.get("file")
        if uploaded_file:
            content = uploaded_file.read().decode("utf-8", errors="ignore")
            for line in content.splitlines():
                _add_one(line.split(",")[0].strip().strip('"'))

        for email in request.data.get("emails", []):
            _add_one(str(email))

        return Response({"added": added, "skipped_duplicates": skipped})


class CampaignRecipientDetailView(APIView):
    """
    PATCH  /api/mail/campaigns/<pk>/recipients/<rid>/   → edit name
    DELETE /api/mail/campaigns/<pk>/recipients/<rid>/   → remove
    """
    def get_permissions(self):
        if self.request.method == "DELETE":
            return [IsAuthenticated(), CanDeleteBulkMail()]
        return [IsAuthenticated(), CanEditBulkMail()]

    def _get_recipient(self, pk, rid, group_id):
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
        if new_name := request.data.get("name", "").strip():
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
    """
    permission_classes = [IsAuthenticated, CanSendBulkMail]

    def post(self, request, pk):
        obj = _get_campaign(pk, get_group_id(request.user))
        if not obj:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if not obj.subject or not obj.body:
            return Response(
                {"error": "No email draft saved. Click 'Edit Draft' to write the subject and body first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        recipients = list(obj.recipients.all())
        if not recipients:
            return Response(
                {"error": "No recipients in this campaign. Click 'People' to add emails first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        messages = tuple(
            (
                obj.subject,
                f"Dear {r.name},\n\n{obj.body}",
                settings.EMAIL_HOST_USER,
                [r.email],
            )
            for r in recipients
        )

        def _send_all():
            send_mass_mail(messages, fail_silently=True)

        threading.Thread(target=_send_all, daemon=True).start()

        return Response(
            {"queued": True, "total_recipients": len(recipients)},
            status=status.HTTP_200_OK,
        )