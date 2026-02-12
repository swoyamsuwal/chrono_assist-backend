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

class RoleViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        group_id = get_group_id(self.request.user)
        return Role.objects.filter(group_id=group_id).prefetch_related("perms")

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return RoleCreateUpdateSerializer
        return RoleSerializer

    def get_permissions(self):
        perms = [IsAuthenticated(), CanViewPermissionModule()]

        if self.action == "create":
            perms.append(CanCreateRole())
        elif self.action in ["update", "partial_update"]:
            perms.append(CanUpdateRole())
        elif self.action == "destroy":
            perms.append(CanDeleteRole())

        return perms
