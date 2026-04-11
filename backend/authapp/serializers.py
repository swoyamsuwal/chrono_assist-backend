# ===============================================================
#  authapp/serializers.py
#  Converts User model instances to/from JSON for API requests
#  Three serializers handle different use cases: create, profile, role-update
# ===============================================================


# ---------------- Step 0: Imports ----------------
from rest_framework import serializers
from django.contrib.auth import get_user_model
User = get_user_model()  # Always use get_user_model() to get the custom User, not import directly

from rbac.models import Role
from file_upload.utils import get_group_id  # Helper to resolve which company a user belongs to


# ================================================================
#  Serializer 1: UserSerializer
#  Purpose: Used for CREATING new users (register & sub-register)
#  Handles password hashing and user_type assignment
# ================================================================
class UserSerializer(serializers.ModelSerializer):

    # ---------------- Step 1a: Extra Fields ----------------
    # password is write_only → never returned in API responses (security)
    password = serializers.CharField(write_only=True)
    # user_type is write_only → client can send it, but it's overridden in sub_register_api anyway
    user_type = serializers.ChoiceField(choices=User.UserType.choices, write_only=True, default=User.UserType.MAIN)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "user_type", "role"]
        read_only_fields = ["id"]  # ID is DB-generated, never set by client

    # ---------------- Step 1b: Custom Create Logic ----------------
    def create(self, validated_data):
        # Pop fields that don't map directly to User model constructor
        user_type = validated_data.pop('user_type', User.UserType.MAIN)
        password = validated_data.pop('password')

        # Build user object but don't save yet — we need to hash the password first
        user = User(**validated_data)
        user.set_password(password)  # Hashes the plain-text password using Django's PBKDF2
        user.user_type = user_type
        user.save()  # ID is generated at this point
        return user


# ================================================================
#  Serializer 2: ProfileSerializer
#  Purpose: GET and PUT for /profile/ endpoint
#  Handles profile picture upload and basic info updates
# ================================================================
class ProfileSerializer(serializers.ModelSerializer):

    # ---------------- Step 2a: Profile Picture Handling ----------------
    # profile_picture → writable FileField (accepts uploads)
    # profile_picture_url → read-only computed field (returns the full URL to the file)
    profile_picture = serializers.FileField(required=False, allow_null=True, use_url=True)
    profile_picture_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email",
                  "profile_picture", "profile_picture_url", "user_type"]
        read_only_fields = ["id", "email"]  # Email cannot be changed via profile endpoint

    # ---------------- Step 2b: Compute Profile Picture URL ----------------
    # SerializerMethodField calls this to build the file URL
    # Safe fallback: returns None if file doesn't exist or URL generation fails
    def get_profile_picture_url(self, obj):
        file = getattr(obj, "profile_picture", None)
        if file:
            try:
                return file.url  # MinIO signed URL or relative path
            except Exception:
                return None
        return None


# ================================================================
#  Serializer 3: UserRoleUpdateSerializer
#  Purpose: PATCH /users/<id>/role/ — only updates the role FK
#  Validates that the new role belongs to the same company (group_id check)
# ================================================================
class UserRoleUpdateSerializer(serializers.ModelSerializer):

    # ---------------- Step 3a: Role ID Field ----------------
    # role_id maps to the "role" FK on User
    # PrimaryKeyRelatedField → client sends an integer ID, DRF resolves it to a Role object
    role_id = serializers.PrimaryKeyRelatedField(
        source="role",
        queryset=Role.objects.all(),
        required=True
    )

    class Meta:
        model = User
        fields = ["role_id"]

    # ---------------- Step 3b: Company Isolation Validation ----------------
    # Prevents a MAIN user from assigning a role that belongs to a different company
    # group_id is the "company namespace" — roles are scoped to it
    def validate(self, attrs):
        request = self.context["request"]
        me = request.user
        group_id = get_group_id(me)  # Resolves to me.id if MAIN, or me.follow_user_id if SUB

        role_obj = attrs["role"]
        if role_obj.group_id != group_id:
            # Role exists but belongs to a different company — reject it
            raise serializers.ValidationError({"role_id": "Invalid role for this company."})

        return attrs