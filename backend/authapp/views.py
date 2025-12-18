from datetime import timedelta

from django.utils import timezone
from django.contrib.auth import authenticate, login, get_user_model
from django.views.decorators.csrf import ensure_csrf_cookie

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .serializers import UserSerializer, ProfileSerializer
from .utils import send_otp_email, generate_otp_code

User = get_user_model()

# ---------- CSRF ----------

@ensure_csrf_cookie
@api_view(['GET'])
@permission_classes([AllowAny])
def get_csrf(request):
    return Response({"message": "CSRF cookie set"})

# ---------- REGISTER ----------

@api_view(['POST'])
@permission_classes([AllowAny])
def register_api(request):
    serializer = UserSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Save user from validated serializer
    user = serializer.save()

    # Correct mapping
    user.username = serializer.validated_data["username"]   # <-- name
    user.email = serializer.validated_data["email"]         # <-- email
    user.set_password(serializer.validated_data["password"])
    user.save()

    # Optional: login to create a session
    login(request, user, backend='authapp.auth_backend.EmailAuthBackend')


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

# ---------- helper: set OTP in user.metadata ----------

def set_login_otp_on_user(user: User, ttl_minutes: int = 5) -> None:
    code = generate_otp_code()
    expires_at = timezone.now() + timedelta(minutes=ttl_minutes)

    meta = user.metadata or {}
    meta["otp"] = {
        "code": code,
        "purpose": "login",
        "expires_at": expires_at.isoformat(),
        "attempts": 0,
        "is_used": False,
    }
    user.metadata = meta
    user.save(update_fields=["metadata"])

    send_otp_email(user.email, code, purpose="Login")

# ---------- LOGIN STEP 1 (email + password -> send OTP) ----------

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
        # Find user by email
        user_obj = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    # Authenticate using username from DB
    user = authenticate(request, email=email, password=password)

    if user is None:
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        return Response(
            {"error": "User account is inactive."},
            status=status.HTTP_403_FORBIDDEN,
        )

    set_login_otp_on_user(user, ttl_minutes=5)

    return Response(
        {
            "message": "OTP sent to email",
            "otp_required": True,
            "email": user.email,
        },
        status=status.HTTP_200_OK,
    )

# ---------- VERIFY OTP STEP 2 ----------

@api_view(["POST"])
@permission_classes([AllowAny])
def verify_otp_api(request):
    email = request.data.get("email")
    code = request.data.get("code")

    if not email or not code:
        return Response(
            {"error": "email and code are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"error": "User not found."}, status=status.HTTP_400_BAD_REQUEST)

    meta = user.metadata or {}
    otp_data = meta.get("otp")

    if not otp_data:
        return Response({"error": "No OTP pending."}, status=status.HTTP_400_BAD_REQUEST)

    if otp_data.get("is_used"):
        return Response({"error": "OTP already used."}, status=status.HTTP_400_BAD_REQUEST)

    expires_at_str = otp_data.get("expires_at")
    try:
        expires_at = timezone.datetime.fromisoformat(expires_at_str)
        if timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at, timezone.utc)
    except Exception:
        return Response({"error": "Invalid OTP data."}, status=status.HTTP_400_BAD_REQUEST)

    if timezone.now() > expires_at:
        return Response({"error": "OTP expired."}, status=status.HTTP_400_BAD_REQUEST)

    if otp_data.get("code") != code:
        otp_data["attempts"] = int(otp_data.get("attempts", 0)) + 1
        meta["otp"] = otp_data
        user.metadata = meta
        user.save(update_fields=["metadata"])
        return Response({"error": "Incorrect OTP."}, status=status.HTTP_400_BAD_REQUEST)

    # Mark OTP used
    otp_data["is_used"] = True
    meta["otp"] = otp_data
    user.metadata = meta
    user.save(update_fields=["metadata"])

    if not user.is_active:
        return Response({"error": "User not available."}, status=status.HTTP_400_BAD_REQUEST)

    # Keep session
    login(request, user, backend='authapp.auth_backend.EmailAuthBackend')


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

@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def profile_api(request):
    """
    GET -> return current user's profile
    PUT -> update username, first_name, last_name, profile_picture
           (partial updates allowed, JSON or multipart)
    """
    user = request.user

    if request.method == "GET":
        serializer = ProfileSerializer(user)
        return Response(serializer.data)

    serializer = ProfileSerializer(user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    print("Profile validation errors:", serializer.errors)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)