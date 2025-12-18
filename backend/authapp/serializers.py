from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]
        read_only_fields = ["id"]


class ProfileSerializer(serializers.ModelSerializer):
    # Optional file upload
    profile_picture = serializers.FileField(
        required=False,
        allow_null=True,
        use_url=True,
    )
    profile_picture_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "profile_picture",
            "profile_picture_url",
        ]
        read_only_fields = ["id", "email"]

    def get_profile_picture_url(self, obj):
        file = getattr(obj, "profile_picture", None)
        if file:
            try:
                return file.url
            except Exception:
                return None
        return None
