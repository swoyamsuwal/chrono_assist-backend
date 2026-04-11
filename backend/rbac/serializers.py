# ===============================================================
#  rbac/serializers.py
#  Two serializer strategies for roles:
#
#  RoleSerializer           → READ (GET) — returns role + all permission grants
#  RoleCreateUpdateSerializer → WRITE (POST/PATCH) — accepts name + permissions array,
#                               handles validation, creation, and replacement of grants
#
#  RolePermissionSerializer → shared inner serializer used by both above
# ===============================================================


# ---------------- Step 0: Imports ----------------
from rest_framework import serializers
from .models import Role, RolePermission, Feature, Action
from authapp.utils import get_group_id  # Resolves company group_id from user


# ================================================================
#  Serializer 1: RolePermissionSerializer
#  Represents a single permission grant: { id, feature, action }
#  Used nested inside RoleSerializer (read) and RoleCreateUpdateSerializer (write)
# ================================================================
class RolePermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RolePermission
        fields = ["id", "feature", "action"]
        read_only_fields = ["id"]  # ID is assigned by DB on create


# ================================================================
#  Serializer 2: RoleSerializer
#  READ-ONLY serializer used for GET requests
#  Returns the full role including all nested permission grants
#  group_id is read-only — never accepted from the client
# ================================================================
class RoleSerializer(serializers.ModelSerializer):
    # Nested read-only list of permission grants for this role
    # related_name="perms" on RolePermission.role enables role.perms.all()
    perms = RolePermissionSerializer(many=True, read_only=True)

    class Meta:
        model = Role
        fields = ["id", "group_id", "name", "perms"]
        read_only_fields = ["id", "group_id"]  # group_id is set server-side, never from client


# ================================================================
#  Serializer 3: RoleCreateUpdateSerializer
#  WRITE serializer used for POST (create) and PATCH/PUT (update)
#  Accepts a "permissions" array and handles full replacement on update
#
#  Key design decisions:
#   - group_id is excluded from fields → always taken from the authenticated user
#   - permissions is write_only → never echoed back in the response
#   - On update, permissions are fully replaced (delete all → bulk_create new)
# ================================================================
class RoleCreateUpdateSerializer(serializers.ModelSerializer):

    # ---------------- Step 3a: Permissions Input Field ----------------
    # write_only=True → accepted on input but not returned in response
    # required=False  → a role can be created without any permissions initially
    permissions = RolePermissionSerializer(many=True, write_only=True, required=False)

    class Meta:
        model = Role
        # group_id is intentionally excluded — it's always resolved server-side
        fields = ["id", "name", "permissions"]
        read_only_fields = ["id"]

    # ================================================================
    #  validate_permissions
    #  Field-level validator called automatically by DRF before create/update
    #  Checks:
    #   1. Each feature is a valid Feature enum value
    #   2. Each action is a valid Action enum value
    #   3. No duplicate (feature, action) pairs in the same request
    # ================================================================
    def validate_permissions(self, value):
        # Build sets of valid choices from the TextChoices enums
        # This ensures validation stays in sync if new features/actions are added
        valid_features = {c[0] for c in Feature.choices}
        valid_actions  = {c[0] for c in Action.choices}

        # ---------------- Step 3b: Validate Each Permission Entry ----------------
        for p in value:
            if p["feature"] not in valid_features:
                raise serializers.ValidationError(f"Invalid feature: {p['feature']}")
            if p["action"] not in valid_actions:
                raise serializers.ValidationError(f"Invalid action: {p['action']}")

        # ---------------- Step 3c: Check for Duplicates Within the Request ----------------
        # The DB unique_together on RolePermission would catch this, but we validate
        # here first to return a clean error message instead of a DB IntegrityError
        seen = set()
        for p in value:
            key = (p["feature"], p["action"])
            if key in seen:
                raise serializers.ValidationError(f"Duplicate permission: {key}")
            seen.add(key)

        return value

    # ================================================================
    #  create
    #  Called by RoleViewSet on POST /rbac/roles/
    #  Flow:
    #   Step 1 → Resolve group_id from the requesting user (never from client)
    #   Step 2 → Pop permissions out of validated_data before Role.objects.create()
    #   Step 3 → Enforce unique role name per company at the serializer level
    #   Step 4 → Create the Role row
    #   Step 5 → Bulk-create all RolePermission rows
    # ================================================================
    def create(self, validated_data):
        request  = self.context["request"]
        user     = request.user

        # ---------------- Step 1: Resolve Company Group ----------------
        # group_id comes from the authenticated user — client cannot override this
        group_id = get_group_id(user)

        # ---------------- Step 2: Separate Permissions from Role Data ----------------
        # validated_data after pop() = { "name": "Admin" }
        permissions_data = validated_data.pop("permissions", [])

        # ---------------- Step 3: Unique Name Check ----------------
        # unique_together on the model handles this at DB level, but we check early
        # here to return a clean {"name": ["Role name already exists..."]} error
        # instead of an opaque IntegrityError 500
        if Role.objects.filter(group_id=group_id, name=validated_data.get("name")).exists():
            raise serializers.ValidationError({"name": ["Role name already exists in this company."]})

        # ---------------- Step 4: Create Role ----------------
        role = Role.objects.create(group_id=group_id, **validated_data)

        # ---------------- Step 5: Bulk Create Permission Grants ----------------
        # bulk_create() inserts all rows in a single SQL INSERT → more efficient than
        # individual .create() calls inside a loop
        if permissions_data:
            RolePermission.objects.bulk_create([
                RolePermission(role=role, feature=p["feature"], action=p["action"])
                for p in permissions_data
            ])

        return role

    # ================================================================
    #  update
    #  Called by RoleViewSet on PATCH or PUT /rbac/roles/<id>/
    #  Flow:
    #   Step 1 → Pop permissions from validated_data (None if not sent = no change)
    #   Step 2 → Update the role name if provided
    #   Step 3 → If permissions were sent, fully replace all existing grants
    #            (delete old rows → bulk_create new rows)
    #
    #  NOTE: permissions=None (key absent) → no change to existing grants
    #        permissions=[]   (key present, empty) → removes ALL grants from the role
    # ================================================================
    def update(self, instance, validated_data):
        # ---------------- Step 1: Separate Permissions ----------------
        # None = key was absent from the request → don't touch existing permissions
        # []   = key was present but empty → wipe all permissions from the role
        permissions_data = validated_data.pop("permissions", None)

        # ---------------- Step 2: Update Role Name ----------------
        # update_fields=["name"] → issues a targeted UPDATE only for the name column
        # More efficient than a full-row save and prevents accidental overwrites
        instance.name = validated_data.get("name", instance.name)
        instance.save(update_fields=["name"])

        # ---------------- Step 3: Replace Permissions (if provided) ----------------
        if permissions_data is not None:
            # Delete all existing grants for this role (full replacement strategy)
            # This is simpler and safer than diffing old vs new permissions
            instance.perms.all().delete()

            # Re-create the new set of grants in one SQL INSERT
            if permissions_data:
                RolePermission.objects.bulk_create([
                    RolePermission(role=instance, feature=p["feature"], action=p["action"])
                    for p in permissions_data
                ])

        return instance