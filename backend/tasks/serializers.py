from django.contrib.auth import get_user_model
from rest_framework import serializers

from file_upload.utils import get_group_id
from .models import Task
from .utils import same_group

User = get_user_model()


class TaskUserMiniSerializer(serializers.ModelSerializer):
    profile_picture_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "profile_picture_url"]

    def get_profile_picture_url(self, obj):
        f = getattr(obj, "profile_picture", None)
        if not f:
            return None

        try:
            url = f.url
        except Exception:
            return None

        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url  # absolute is safer for frontend [web:77]


class TaskCreateSerializer(serializers.ModelSerializer):
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "short_description",
            "full_description",
            "deadline",
            "assigned_to",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_by", "created_at", "updated_at"]

    def validate_assigned_to(self, user):
        if not same_group(self.context["request"].user, user):
            raise serializers.ValidationError("assigned_to must be from same group.")
        return user

    def create(self, validated_data):
        request = self.context["request"]
        return Task.objects.create(
            follow_group=get_group_id(request.user),
            created_by=request.user,
            status=Task.Status.TASK,
            **validated_data,
        )


class TaskUpdateSerializer(serializers.ModelSerializer):
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)

    class Meta:
        model = Task
        fields = ["title", "short_description", "full_description", "deadline", "assigned_to", "status"]

    def validate_assigned_to(self, user):
        if not same_group(self.context["request"].user, user):
            raise serializers.ValidationError("assigned_to must be from same group.")
        return user


class TaskDetailSerializer(serializers.ModelSerializer):
    assigned_to = TaskUserMiniSerializer(read_only=True)
    created_by = TaskUserMiniSerializer(read_only=True)

    class Meta:
        model = Task
        fields = "__all__"
