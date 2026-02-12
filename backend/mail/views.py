from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from django.core.mail import send_mail
from django.conf import settings

from .serializers import GenerateEmailSerializer, SendEmailSerializer
from .llm_client import generate_email_draft

from .rbac_perms import CanViewMail, CanSendMail


class GenerateEmailView(APIView):
    # “view/use mail feature” permission
    permission_classes = [IsAuthenticated, CanViewMail]

    def post(self, request):
        serializer = GenerateEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        prompt = serializer.validated_data["prompt"]
        tone = serializer.validated_data["tone"]

        draft = generate_email_draft(prompt, tone)
        return Response(draft, status=status.HTTP_200_OK)


class SendEmailView(APIView):
    # sending is an “execute” permission
    permission_classes = [IsAuthenticated, CanSendMail]

    def post(self, request):
        serializer = SendEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        subject = serializer.validated_data["subject"]
        body = serializer.validated_data["body"]
        recipient = serializer.validated_data["recipient"]

        sent = send_mail(
            subject=subject,
            message=body,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[recipient],
            fail_silently=False,
        )

        return Response({"sent": bool(sent)}, status=status.HTTP_200_OK)
