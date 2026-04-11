# ===============================================================
#  rbac/views.py
#  Single ViewSet managing the full lifecycle of Role objects
#
#  ENDPOINT MAP (via DefaultRouter):
#   GET    /rbac/roles/          → list all roles for this company
#   POST   /rbac/roles/          → create a new role
#   GET    /rbac/roles/<id>/     → retrieve a single role with permissions
#   PATCH  /rbac/roles/<id>/     → update role name and/or permissions
#   DELETE /rbac/roles/<id>/     → delete the role and all its permission grants
#
#  PERMISSION STRATEGY:
#   CanViewPermissionModule → required for ALL actions (base gate)
#   CanCreateRole           → additionally required for create
#   CanUpdateRole           → additionally required for update/partial_update
#   CanDeleteRole           → additionally required for destroy
# ===============================================================


# ---------------- Step 0: Imports ----------------
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from authapp.utils import get_group_id
from .models import Role
from .serializers import RoleSerializer, RoleCreateUpdateSerializer
from .rbac_perms import (
    CanViewPermissionModule,
    CanCreateRole,
    CanUpdateRole,
    CanDeleteRole,
)


# ================================================================
#  ViewSet: RoleViewSet
#  ModelViewSet provides list, create, retrieve, update, partial_update,
#  and destroy actions automatically — we only customize permissions,
#  queryset scoping, and serializer selection
# ================================================================
class RoleViewSet(viewsets.ModelViewSet):
    # IsAuthenticated is the baseline — all actions require a logged-in user
    permission_classes = [IsAuthenticated]

    # ================================================================
    #  get_queryset
    #  Scopes the queryset to only the roles belonging to the requesting
    #  user's company (group_id) — prevents cross-company data leaks
    #  prefetch_related("perms") → avoids N+1 queries when the serializer
    #  iterates over role.perms.all() for each role in the list
    # ================================================================
    def get_queryset(self):
        group_id = get_group_id(self.request.user)
        return Role.objects.filter(group_id=group_id).prefetch_related("perms")

    # ================================================================
    #  get_serializer_class
    #  Two serializer strategies based on the action:
    #
    #  WRITE actions (create, update, partial_update):
    #   → RoleCreateUpdateSerializer — accepts "permissions" array, handles
    #     group_id injection, validation, and bulk_create of RolePermissions
    #
    #  READ actions (list, retrieve):
    #   → RoleSerializer — returns role + nested permission grants (read-only view)
    # ================================================================
    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return RoleCreateUpdateSerializer
        return RoleSerializer

    # ================================================================
    #  get_permissions
    #  Builds the permission list dynamically based on the action
    #
    #  DESIGN: CanViewPermissionModule is always included first as a base gate
    #  Then a second, action-specific permission is appended on top:
    #
    #   list / retrieve              → [IsAuthenticated, CanViewPermissionModule]
    #   create                       → [IsAuthenticated, CanViewPermissionModule, CanCreateRole]
    #   update / partial_update      → [IsAuthenticated, CanViewPermissionModule, CanUpdateRole]
    #   destroy                      → [IsAuthenticated, CanViewPermissionModule, CanDeleteRole]
    #
    #  This stacking means a user needs BOTH "permission:view" AND "permission:create"
    #  to create roles — fine-grained control without needing a separate view
    # ================================================================
    def get_permissions(self):
        # ---------------- Step 1: Base Permission (all actions) ----------------
        perms = [IsAuthenticated(), CanViewPermissionModule()]

        # ---------------- Step 2: Action-Specific Permission ----------------
        if self.action == "create":
            perms.append(CanCreateRole())
        elif self.action in ["update", "partial_update"]:
            perms.append(CanUpdateRole())
        elif self.action == "destroy":
            perms.append(CanDeleteRole())

        return perms