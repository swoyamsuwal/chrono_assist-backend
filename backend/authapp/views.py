from django.utils import timezone
from django.contrib.auth import authenticate, login, get_user_model
from django.views.decorators.csrf import ensure_csrf_cookie

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from .serializers import UserSerializer
from .models import OtpCode
from .utils import send_otp_email

User = get_user_model()

# ---------- CSRF ----------

@ensure_csrf_cookie
@api_view(['GET'])
@permission_classes([AllowAny])
def get_csrf(request):
    return Response({"message": "CSRF cookie set"})

# ---------- REGISTER (no OTP yet) ----------

@api_view(['POST'])
@permission_classes([AllowAny])
def register_api(request):
    serializer = UserSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()
    user.set_password(serializer.validated_data["password"])
    user.save()

    # auto-login after register (no OTP for now)
    login(request, user)

    return Response(
        {
            "message": "User registered successfully",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
            },
        },
        status=status.HTTP_201_CREATED,
    )

# ---------- LOGIN (step 1: email + password -> send OTP) ----------

@api_view(["POST"])
@permission_classes([AllowAny])
def login_api(request):
    email = request.data.get("email")
    password = request.data.get("password")

    if not email or not password:
        return Response(
            {"error": "Email and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # find user by email
        user_obj = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    # authenticate using username under the hood
    user = authenticate(request, username=user_obj.username, password=password)

    if user is None:
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        return Response(
            {"error": "User account is inactive."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # 1) create OTP
    otp_obj = OtpCode.create_for_user(user, purpose="login")

    # 2) send email
    send_otp_email(user.email, otp_obj.code, purpose="Login")

    # 3) return info for frontend (NO login() yet)
    return Response(
        {
            "message": "OTP sent to email",
            "otp_required": True,
            "otp_id": str(otp_obj.id),  # frontend stores this
            "email": user.email,
        },
        status=status.HTTP_200_OK,
    )

# ---------- VERIFY OTP (step 2: finish login) ----------

@api_view(["POST"])
@permission_classes([AllowAny])
def verify_otp_api(request):
    otp_id = request.data.get("otp_id")
    code = request.data.get("code")

    if not otp_id or not code:
        return Response(
            {"error": "otp_id and code are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        otp_obj = OtpCode.objects.select_related("user").get(id=otp_id)
    except OtpCode.DoesNotExist:
        return Response({"error": "Invalid OTP session."}, status=status.HTTP_400_BAD_REQUEST)

    if otp_obj.is_used:
        return Response({"error": "OTP already used."}, status=status.HTTP_400_BAD_REQUEST)

    if timezone.now() > otp_obj.expires_at:
        return Response({"error": "OTP expired."}, status=status.HTTP_400_BAD_REQUEST)

    if otp_obj.code != code:
        otp_obj.attempts += 1
        otp_obj.save(update_fields=["attempts"])
        return Response({"error": "Incorrect OTP."}, status=status.HTTP_400_BAD_REQUEST)

    # mark used
    otp_obj.is_used = True
    otp_obj.save(update_fields=["is_used"])

    user = otp_obj.user
    if user is None or not user.is_active:
        return Response({"error": "User not available."}, status=status.HTTP_400_BAD_REQUEST)

    # now create session
    login(request, user)

    return Response(
        {
            "message": "OTP verified. Login successful.",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
            },
        },
        status=status.HTTP_200_OK,
    )
