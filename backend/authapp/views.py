# ===============================================================
#  authapp/views.py
#  All API views for authentication and user management
#
#  FLOW OVERVIEW:
#  1. CSRF          → frontend fetches cookie before any POST
#  2. Register      → create MAIN user + auto Owner role
#  3. Sub-Register  → create SUB user under a MAIN user
#  4. Login Step 1  → verify email+password → send OTP
#  5. Login Step 2  → verify OTP → create session
#  6. Profile       → GET/PUT current user profile
#  7. List Users    → list all SUB users in the same company
#  8. Update Role   → PATCH a sub-user's role or email
#  9. Delete User   → DELETE a sub-user
#  10. My Perms     → return current user's permission list
# ===============================================================


# ---------------- Step 0: Imports ----------------
from datetime import timedelta

from django.utils import timezone
from django.contrib.auth import authenticate, login, get_user_model
from django.views.decorators.csrf import ensure_csrf_cookie  # Forces CSRF cookie onto response
from django.views.decorators.csrf import csrf_exempt         # Skips CSRF check (used for public register)
from rbac.models import Role, RolePermission
from file_upload.utils import get_group_id  # Resolves the company group_id for any user

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .serializers import UserSerializer, ProfileSerializer, UserRoleUpdateSerializer
from .utils import send_otp_email, generate_otp_code

from .rbac_perms import (
    CanViewPermissionModule,  # Checks role has "permission:view"
    CanCreateAccount,          # Checks role has "permission:create"
    CanUpdateAccount,          # Checks role has "permission:update"
    CanDeleteAccount,          # Checks role has "permission:delete"
)

User = get_user_model()  # Always use this instead of importing User directly


# ================================================================
#  View 1: get_csrf
#  GET /csrf/
#  Purpose: Sets the CSRF cookie on the client (browser/Next.js)
#  Next.js must call this before any POST/PUT/DELETE request
#  @ensure_csrf_cookie → Django attaches csrftoken cookie to this response
# ================================================================
@ensure_csrf_cookie
@api_view(['GET'])
@permission_classes([AllowAny])
def get_csrf(request):
    return Response({"message": "CSRF cookie set"})


# ================================================================
#  View 2: register_api
#  POST /register/
#  Purpose: Self-registration for MAIN (owner) users only
#
#  Flow:
#   Step 1 → Validate request data via UserSerializer
#   Step 2 → Save user, set follow_user = self (MAIN user is their own root)
#   Step 3 → Find the seeded "Owner" template role (group_id=0)
#   Step 4 → Clone that template as a new Owner role for this user's company
#   Step 5 → Assign the new Owner role to this user
#   Step 6 → Log the user in and return user data
# ================================================================
@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def register_api(request):
    # ---------------- Step 1: Validate Input ----------------
    serializer = UserSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()

    # ---------------- Step 2: Mark as MAIN User ----------------
    # MAIN users self-reference themselves — this is what identifies them as the root of a company
    user.follow_user = user

    # ---------------- Step 3: Load Owner Role Template ----------------
    # group_id=0 is a special sentinel — it holds the default "Owner" role permissions
    # seeded in the DB so every new company gets the same starting permissions
    try:
        template_role = Role.objects.prefetch_related("perms").get(
            group_id=0, name="Owner"
        )
        template_perms = list(template_role.perms.all())
    except Role.DoesNotExist:
        template_perms = []  # No template found — user gets a blank role

    # ---------------- Step 4: Create This User's Owner Role ----------------
    # Each company gets its own copy of the Owner role (scoped to group_id=user.id)
    # This way, each company can later customize their own Owner permissions independently
    owner_role = Role.objects.create(group_id=user.id, name="Owner")
    if template_perms:
        # Bulk insert all permissions from the template into the new role
        RolePermission.objects.bulk_create([
            RolePermission(role=owner_role, feature=p.feature, action=p.action)
            for p in template_perms
        ])

    # ---------------- Step 5: Assign Role + Save ----------------
    user.role = owner_role
    user.save(update_fields=["follow_user", "role"])

    # ---------------- Step 6: Auto-Login + Return Response ----------------
    # Log the user in immediately after registration — no separate login step needed
    login(request, user, backend="authapp.auth_backend.EmailAuthBackend")

    return Response(
        {
            "message": "User registered successfully",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "user_type": user.user_type,
                "follow_user": user.follow_user_id if user.follow_user else None,
                "role": user.role.name if user.role else None,
            },
        },
        status=status.HTTP_201_CREATED,
    )


# ================================================================
#  View 3: sub_register_api
#  POST /sub-register/
#  Purpose: MAIN user creates a SUB (staff) user under their company
#  Requires: IsAuthenticated + CanCreateAccount (RBAC permission check)
#
#  Flow:
#   Step 1 → Validate that role_id is provided and belongs to this company
#   Step 2 → Validate and save the new user via UserSerializer
#   Step 3 → Mark new user as SUB, link to MAIN user, assign role
# ================================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated, CanCreateAccount])
def sub_register_api(request):
    main_user = request.user
    # group_id = the company namespace (main_user.id for MAIN, or follow_user_id for SUB)
    group_id = get_group_id(main_user)

    # ---------------- Step 1: Validate Role ----------------
    role_id = request.data.get("role_id")
    if not role_id:
        return Response({"error": "role_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Role must exist AND belong to this company (group_id check prevents cross-company role assignment)
        role = Role.objects.get(id=role_id, group_id=group_id)
    except Role.DoesNotExist:
        return Response({"error": "Invalid role for this company"}, status=status.HTTP_400_BAD_REQUEST)

    # ---------------- Step 2: Validate and Create User ----------------
    serializer = UserSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    sub_user = serializer.save()

    # ---------------- Step 3: Configure Sub User ----------------
    # SUB type → not an owner, staff member
    # follow_user → links to MAIN user for company grouping
    # role → the role selected by the MAIN user
    sub_user.user_type = User.UserType.SUB
    sub_user.follow_user = main_user
    sub_user.role = role
    sub_user.save(update_fields=['user_type', 'follow_user', 'role'])

    return Response(
        {
            "message": "Sub user registered successfully",
            "user": {
                "id": sub_user.id,
                "username": sub_user.username,
                "email": sub_user.email,
                "user_type": sub_user.user_type,
                "follow_user": sub_user.follow_user_id if sub_user.follow_user else None,
                "role": sub_user.role.name if sub_user.role else None,
                "role_id": sub_user.role_id,
            },
        },
        status=status.HTTP_201_CREATED,
    )


# ================================================================
#  Helper: set_login_otp_on_user
#  Called internally by login_api to generate and store an OTP
#  Stores OTP data inside user.metadata["otp"] (no separate table needed)
#
#  OTP structure stored in metadata:
#   {
#     "code": "482910",
#     "purpose": "login",
#     "expires_at": "2024-...",
#     "attempts": 0,
#     "is_used": False
#   }
# ================================================================
def set_login_otp_on_user(user: User, ttl_minutes: int = 5) -> None:
    # ---------------- Step 1: Generate Code + Expiry ----------------
    code = generate_otp_code()
    expires_at = timezone.now() + timedelta(minutes=ttl_minutes)

    # ---------------- Step 2: Write OTP into user.metadata ----------------
    # metadata is a JSONField — we just update the "otp" key
    meta = user.metadata or {}
    meta["otp"] = {
        "code": code,
        "purpose": "login",
        "expires_at": expires_at.isoformat(),  # Store as ISO string for easy parsing later
        "attempts": 0,
        "is_used": False,
    }
    user.metadata = meta
    user.save(update_fields=["metadata"])  # Only update metadata column, not entire row

    # ---------------- Step 3: Send Email ----------------
    send_otp_email(user.email, code, purpose="Login")


# ================================================================
#  View 4: login_api   (Login Step 1 of 2)
#  POST /login/
#  Purpose: Validate email+password → send OTP → return otp_required flag
#  Does NOT create a session yet — session is only created after OTP is verified
#
#  Flow:
#   Step 1 → Check email + password fields present
#   Step 2 → Lookup user by email, then authenticate credentials
#   Step 3 → Check account is active
#   Step 4 → Generate OTP, store in metadata, send email
# ================================================================
@api_view(["POST"])
@permission_classes([AllowAny])
def login_api(request):
    # ---------------- Step 1: Extract Credentials ----------------
    email = request.data.get("email")
    password = request.data.get("password")

    if not email or not password:
        return Response(
            {"error": "Email and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ---------------- Step 2: Verify Credentials ----------------
    try:
        user_obj = User.objects.get(email=email)  # Check user exists by email
    except User.DoesNotExist:
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    # authenticate() calls our custom EmailAuthBackend, checks password hash
    user = authenticate(request, email=email, password=password)

    if user is None:
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    # ---------------- Step 3: Check Account Status ----------------
    if not user.is_active:
        return Response(
            {"error": "User account is inactive."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # ---------------- Step 4: Generate + Send OTP ----------------
    # OTP is stored in user.metadata so no extra table is needed
    set_login_otp_on_user(user, ttl_minutes=5)

    # Tell frontend: "credentials ok, now submit the OTP code"
    return Response(
        {
            "message": "OTP sent to email",
            "otp_required": True,
            "email": user.email,
        },
        status=status.HTTP_200_OK,
    )


# ================================================================
#  View 5: verify_otp_api   (Login Step 2 of 2)
#  POST /verify-otp/
#  Purpose: Verify the OTP code → create Django session → user is now logged in
#
#  Flow:
#   Step 1 → Validate email + code fields
#   Step 2 → Load user and extract OTP from metadata
#   Step 3 → Check is_used, expiry, and code match
#   Step 4 → Mark OTP as used, create session via login()
# ================================================================
@api_view(["POST"])
@permission_classes([AllowAny])
def verify_otp_api(request):
    # ---------------- Step 1: Extract Input ----------------
    email = request.data.get("email")
    code = request.data.get("code")

    if not email or not code:
        return Response(
            {"error": "email and code are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ---------------- Step 2: Load User + OTP Data ----------------
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"error": "User not found."}, status=status.HTTP_400_BAD_REQUEST)

    meta = user.metadata or {}
    otp_data = meta.get("otp")

    if not otp_data:
        return Response({"error": "No OTP pending."}, status=status.HTTP_400_BAD_REQUEST)

    # ---------------- Step 3a: Check OTP Already Used ----------------
    if otp_data.get("is_used"):
        return Response({"error": "OTP already used."}, status=status.HTTP_400_BAD_REQUEST)

    # ---------------- Step 3b: Check OTP Expiry ----------------
    expires_at_str = otp_data.get("expires_at")
    try:
        expires_at = timezone.datetime.fromisoformat(expires_at_str)
        if timezone.is_naive(expires_at):
            # Make timezone-aware if it was stored without tzinfo
            expires_at = timezone.make_aware(expires_at, timezone.utc)
    except Exception:
        return Response({"error": "Invalid OTP data."}, status=status.HTTP_400_BAD_REQUEST)

    if timezone.now() > expires_at:
        return Response({"error": "OTP expired."}, status=status.HTTP_400_BAD_REQUEST)

    # ---------------- Step 3c: Check Code Match ----------------
    if otp_data.get("code") != code:
        # Wrong code — increment attempt counter and save
        otp_data["attempts"] = int(otp_data.get("attempts", 0)) + 1
        meta["otp"] = otp_data
        user.metadata = meta
        user.save(update_fields=["metadata"])
        return Response({"error": "Incorrect OTP."}, status=status.HTTP_400_BAD_REQUEST)

    # ---------------- Step 4: Mark OTP Used + Create Session ----------------
    # is_used=True prevents OTP replay attacks (same code used twice)
    otp_data["is_used"] = True
    meta["otp"] = otp_data
    user.metadata = meta
    user.save(update_fields=["metadata"])

    if not user.is_active:
        return Response({"error": "User not available."}, status=status.HTTP_400_BAD_REQUEST)

    # login() creates a Django session → Next.js receives sessionid cookie
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


# ================================================================
#  View 6: profile_api
#  GET/PUT /profile/
#  Purpose: Read or update the currently logged-in user's profile
#  partial=True on PUT means not all fields need to be sent
# ================================================================
@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def profile_api(request):
    user = request.user

    # ---------------- Step 1: GET → Return Profile ----------------
    if request.method == "GET":
        serializer = ProfileSerializer(user)
        return Response(serializer.data)

    # ---------------- Step 2: PUT → Update Profile ----------------
    # partial=True → client can send only the fields they want to change
    serializer = ProfileSerializer(user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    print("Profile validation errors:", serializer.errors)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ================================================================
#  View 7: list_users_api
#  GET /list_users/
#  Purpose: Return all SUB users that belong to the current user's company
#  Requires: IsAuthenticated + CanViewPermissionModule (RBAC check)
#
#  Flow:
#   Step 1 → Resolve group_id (company namespace)
#   Step 2 → Query all SUB users under that group_id
#   Step 3 → Build response with profile picture absolute URLs
# ================================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated, CanViewPermissionModule])
def list_users_api(request):
    me = request.user
    # group_id = me.id (if MAIN) or me.follow_user_id (if SUB viewing their own company)
    group_id = me.follow_user_id or me.id

    # ---------------- Step 1: Query Sub Users ----------------
    # Only returns SUB users — MAIN user themselves is excluded
    qs = (
        User.objects
        .filter(follow_user_id=group_id, user_type=User.UserType.SUB)
        .order_by("id")
    )

    # ---------------- Step 2: Build Response Data ----------------
    data = []
    for u in qs:
        # Build absolute URL for profile picture (MinIO returns a relative path)
        pic = None
        if u.profile_picture:
            try:
                pic = request.build_absolute_uri(u.profile_picture.url)
            except Exception:
                pic = None

        data.append({
            "id":                  u.id,
            "username":            u.username,
            "email":               u.email,
            "user_type":           u.user_type,
            "role":                u.role.name if u.role else None,
            "role_id":             u.role_id,
            "profile_picture_url": pic,
        })

    return Response(data)


# ================================================================
#  View 8: update_user_role_api
#  PATCH /users/<user_id>/role/
#  Purpose: Update a sub-user's role and/or email within the same company
#  Requires: IsAuthenticated + CanUpdateAccount (RBAC check)
#
#  Flow:
#   Step 1 → Verify the target user belongs to this company
#   Step 2 → Handle email update (uniqueness check)
#   Step 3 → Handle role update (company isolation via serializer validation)
#   Step 4 → Refresh from DB and return updated data
# ================================================================
@api_view(["PATCH"])
@permission_classes([IsAuthenticated, CanUpdateAccount])
def update_user_role_api(request, user_id):
    me = request.user
    group_id = get_group_id(me)

    # ---------------- Step 1: Verify Target User ----------------
    # follow_user_id=group_id ensures this sub-user is in the same company
    try:
        target = User.objects.get(id=user_id, follow_user_id=group_id)
    except User.DoesNotExist:
        return Response({"error": "User not found in your company."}, status=status.HTTP_404_NOT_FOUND)

    # ---------------- Step 2: Handle Email Update ----------------
    # Email update is handled manually (not through the role serializer)
    new_email = request.data.get("email", "").strip()
    if new_email and new_email != target.email:
        if User.objects.filter(email=new_email).exclude(id=user_id).exists():
            return Response(
                {"email": ["This email is already in use."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target.email = new_email
        target.save(update_fields=["email"])

    # ---------------- Step 3: Handle Role Update ----------------
    # Only runs if role_id was included in the request body
    # UserRoleUpdateSerializer validates the role belongs to this company
    if "role_id" in request.data:
        serializer = UserRoleUpdateSerializer(
            target, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

    # ---------------- Step 4: Return Fresh Data ----------------
    # refresh_from_db() ensures we return the latest DB state, not stale in-memory values
    target.refresh_from_db()

    return Response({
        "id": target.id,
        "email": target.email,
        "role": target.role.name if target.role else None,
        "role_id": target.role_id,
    })


# ================================================================
#  View 9: delete_user_api
#  DELETE /users/<user_id>/
#  Purpose: Remove a sub-user from the company
#  Requires: IsAuthenticated + CanDeleteAccount (RBAC check)
#
#  Safety checks:
#   - Target must belong to the same company (group_id check)
#   - Cannot delete yourself
# ================================================================
@api_view(["DELETE"])
@permission_classes([IsAuthenticated, CanDeleteAccount])
def delete_user_api(request, user_id):
    me = request.user
    group_id = get_group_id(me)

    # ---------------- Step 1: Verify Target Belongs to This Company ----------------
    try:
        target = User.objects.get(id=user_id, follow_user_id=group_id)
    except User.DoesNotExist:
        return Response({"error": "User not found in your company."}, status=status.HTTP_404_NOT_FOUND)

    # ---------------- Step 2: Self-Delete Protection ----------------
    # Prevents a user from accidentally (or intentionally) deleting their own account
    if target.id == me.id:
        return Response({"error": "You cannot delete your own account."}, status=status.HTTP_400_BAD_REQUEST)

    # ---------------- Step 3: Delete ----------------
    target.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)  # 204 = success with no body


# ================================================================
#  View 10: my_permissions
#  GET /my-permissions/
#  Purpose: Returns the permission list of the currently logged-in user
#  Used by Next.js to determine which UI elements/routes to show or hide
#
#  Logic:
#   - MAIN users have all permissions → return is_main: True (frontend grants full access)
#   - SUB users  → return their actual RolePermission rows as {feature, action} pairs
# ================================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_permissions(request):
    user = request.user

    # ---------------- Step 1: MAIN User Shortcut ----------------
    # MAIN users are the owner — they bypass all permission checks
    if user.user_type == User.UserType.MAIN:
        return Response({"is_main": True, "permissions": []})

    # ---------------- Step 2: SUB User — No Role Assigned ----------------
    if not user.role_id:
        return Response({"is_main": False, "permissions": []})  # No permissions at all

    # ---------------- Step 3: SUB User — Return Role Permissions ----------------
    # Fetch all RolePermission rows for this user's role
    # .values() returns dicts like [{"feature": "permission", "action": "view"}, ...]
    perms = RolePermission.objects.filter(role_id=user.role_id).values("feature", "action")
    return Response({"is_main": False, "permissions": list(perms)})