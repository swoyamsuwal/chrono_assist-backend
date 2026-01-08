from rest_framework import serializers
from django.contrib.auth import get_user_model
User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    user_type = serializers.ChoiceField(choices=User.UserType.choices, write_only=True, default=User.UserType.MAIN)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "user_type","role"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        user_type = validated_data.pop('user_type', User.UserType.MAIN)
        password = validated_data.pop('password')

        user = User(**validated_data)
        user.set_password(password)
        user.user_type = user_type
        user.save()  # ID generated here
        return user

class ProfileSerializer(serializers.ModelSerializer):
    profile_picture = serializers.FileField(required=False, allow_null=True, use_url=True)
    profile_picture_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "profile_picture", "profile_picture_url", "user_type"]
        read_only_fields = ["id", "email"]

    def get_profile_picture_url(self, obj):
        file = getattr(obj, "profile_picture", None)
        if file:
            try:
                return file.url
            except Exception:
                return None
        return None
