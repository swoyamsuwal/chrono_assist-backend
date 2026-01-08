# rbac/serializers.py
from rest_framework import serializers
from .models import Role, RolePermission, Feature, Action
from authapp.utils import get_group_id  # your helper (already used in rbac/permissions.py) [file:21]


class RolePermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RolePermission
        fields = ["id", "feature", "action"]
        read_only_fields = ["id"]


class RoleSerializer(serializers.ModelSerializer):
    """
    Read serializer (GET):
      returns role + perms
    """
    perms = RolePermissionSerializer(many=True, read_only=True)

    class Meta:
        model = Role
        fields = ["id", "group_id", "name", "perms"]
        read_only_fields = ["id", "group_id"]


class RoleCreateUpdateSerializer(serializers.ModelSerializer):
    permissions = RolePermissionSerializer(many=True, write_only=True, required=False)

    class Meta:
        model = Role
        # Don't accept group_id from client
        fields = ["id", "name", "permissions"]
        read_only_fields = ["id"]

    def validate_permissions(self, value):
        valid_features = {c[0] for c in Feature.choices}
        valid_actions = {c[0] for c in Action.choices}

        for p in value:
            if p["feature"] not in valid_features:
                raise serializers.ValidationError(f"Invalid feature: {p['feature']}")
            if p["action"] not in valid_actions:
                raise serializers.ValidationError(f"Invalid action: {p['action']}")

        seen = set()
        for p in value:
            key = (p["feature"], p["action"])
            if key in seen:
                raise serializers.ValidationError(f"Duplicate permission: {key}")
            seen.add(key)

        return value

    def create(self, validated_data):
        request = self.context["request"]
        user = request.user

        group_id = get_group_id(user)
        permissions_data = validated_data.pop("permissions", [])

        # Enforce "unique role name per company" safely
        if Role.objects.filter(group_id=group_id, name=validated_data.get("name")).exists():
            raise serializers.ValidationError({"name": ["Role name already exists in this company."]})

        role = Role.objects.create(group_id=group_id, **validated_data)

        if permissions_data:
            RolePermission.objects.bulk_create(
                [RolePermission(role=role, feature=p["feature"], action=p["action"]) for p in permissions_data]
            )

        return role

    def update(self, instance, validated_data):
        permissions_data = validated_data.pop("permissions", None)

        # Optional safety: don't allow moving role to another group
        instance.name = validated_data.get("name", instance.name)
        instance.save(update_fields=["name"])

        if permissions_data is not None:
            instance.perms.all().delete()
            if permissions_data:
                RolePermission.objects.bulk_create(
                    [RolePermission(role=instance, feature=p["feature"], action=p["action"]) for p in permissions_data]
                )

        return instance
