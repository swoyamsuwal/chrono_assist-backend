from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        # keep it explicit, don't use "__all__"
        fields = ["id", "username", "email", "password"]
        read_only_fields = ["id"]
