# ===============================================================
#  tasks/serializers.py
#  Four serializers for the task lifecycle:
#
#  TaskUserMiniSerializer  → compact user representation (id, name, avatar)
#  TaskCreateSerializer    → validates + creates a new task
#  TaskUpdateSerializer    → validates + partially updates an existing task
#  TaskDetailSerializer    → full task representation for read responses
#                            (embeds full user objects for assigned_to, created_by)
# ===============================================================


# ---------------- Step 0: Imports ----------------
from django.contrib.auth import get_user_model
from rest_framework import serializers

from file_upload.utils import get_group_id
from .models import Task
from .utils import same_group  # Cross-company assignment guard

User = get_user_model()


# ================================================================
#  Serializer 1: TaskUserMiniSerializer
#  A compact user representation embedded in task responses
#  Shows just enough for the board card UI: name, email, and avatar
#  Used as a nested serializer in TaskDetailSerializer
# ================================================================
class TaskUserMiniSerializer(serializers.ModelSerializer):
    # Computed field — generates a full absolute URL for the profile picture
    profile_picture_url = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = ["id", "username", "email", "profile_picture_url"]

    # ---------------- Step 1a: Build Absolute Profile Picture URL ----------------
    def get_profile_picture_url(self, obj):
        # getattr() safely handles users who don't have a profile_picture field
        f = getattr(obj, "profile_picture", None)
        if not f:
            return None

        try:
            url = f.url   # May raise ValueError if the file field has no file attached
        except Exception:
            return None

        # request.build_absolute_uri() → converts "/media/..." to "http://localhost:8000/media/..."
        # This makes the URL usable directly by the Next.js frontend without prefix logic
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url


# ================================================================
#  Serializer 2: TaskCreateSerializer
#  Used by: create_task view (POST /tasks/)
#  Validates the incoming task payload and creates the Task row
#
#  Key design decisions:
#   - status, created_by, follow_group are ALL set server-side (never from client)
#   - assigned_to is validated to ensure it's from the same company
#   - status defaults to TASK on creation (enforced in create(), not the model default)
# ================================================================
class TaskCreateSerializer(serializers.ModelSerializer):
    # PrimaryKeyRelatedField → client sends assigned_to as a user ID integer
    # The full user object is only returned in TaskDetailSerializer (read response)
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

    class Meta:
        model  = Task
        fields = [
            "id", "title", "short_description", "full_description",
            "deadline", "assigned_to", "status",
            "created_by", "created_at", "updated_at",
        ]
        # These fields are set server-side — client cannot override them
        read_only_fields = ["id", "status", "created_by", "created_at", "updated_at"]

    # ---------------- Step 2a: Validate Assignment is Same Company ----------------
    # Called automatically by DRF before create() runs
    # Rejects tasks assigned to users from other companies
    def validate_assigned_to(self, user):
        if not same_group(self.context["request"].user, user):
            raise serializers.ValidationError("assigned_to must be from same group.")
        return user

    # ---------------- Step 2b: Create Task with Server-Side Fields ----------------
    # follow_group → resolves the requesting user's company group
    # created_by   → always the requesting user, never from the client
    # status       → always starts as TASK regardless of what client sends
    def create(self, validated_data):
        request = self.context["request"]
        return Task.objects.create(
            follow_group=get_group_id(request.user),  # Tenant isolation
            created_by=request.user,                   # Authorship
            status=Task.Status.TASK,                   # Force initial status
            **validated_data,
        )


# ================================================================
#  Serializer 3: TaskUpdateSerializer
#  Used by: update_task view (PATCH/PUT /tasks/<pk>/update/)
#  Handles partial updates — all fields are optional (partial=True in the view)
#
#  Key design decision: status is editable here
#  This is how the board's drag-and-drop column change is implemented:
#   PATCH { "status": "IN_PROGRESS" } moves the card to the next column
# ================================================================
class TaskUpdateSerializer(serializers.ModelSerializer):
    # required=False → assigned_to only needs re-validation if the client changes it
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
    )

    class Meta:
        model  = Task
        fields = [
            "title", "short_description", "full_description",
            "deadline", "assigned_to", "status",
        ]
        # status IS editable here — this is the intended update path for status transitions

    # ---------------- Step 3a: Validate Reassignment is Same Company ----------------
    # Only triggered if assigned_to is present in the PATCH body
    def validate_assigned_to(self, user):
        if not same_group(self.context["request"].user, user):
            raise serializers.ValidationError("assigned_to must be from same group.")
        return user


# ================================================================
#  Serializer 4: TaskDetailSerializer
#  Used by: all views for read responses (list, retrieve, after create/update)
#  Returns the complete task with fully expanded user objects for both FKs
#
#  Why a separate read serializer?
#  assigned_to and created_by are sent as IDs on write but need to be
#  returned as full user objects (name + avatar) on read — the board
#  card UI needs this to show the assignee avatar without a second request
# ================================================================
class TaskDetailSerializer(serializers.ModelSerializer):
    # Nested user objects — read_only because this serializer is never used for writes
    assigned_to = TaskUserMiniSerializer(read_only=True)
    created_by  = TaskUserMiniSerializer(read_only=True)

    class Meta:
        model  = Task
        fields = "__all__"  # Return every field — the board needs all task data