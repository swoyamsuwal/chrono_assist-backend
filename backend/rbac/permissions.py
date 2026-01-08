# rbac/permissions.py
from rest_framework.permissions import BasePermission
from authapp.utils import get_group_id
from .models import RolePermission

class HasRBACPermission(BasePermission):
    feature = None
    action = None

    def has_permission(self, request, view):
        user = request.user

        # MAIN user => allow everything (your requirement)
        if getattr(user, "user_type", None) == "main":
            return True

        # No role => deny
        if not user.role_id:
            return False

        # Safety: role must be in same company/group
        group_id = get_group_id(user)
        if user.role.group_id != group_id:
            return False

        return RolePermission.objects.filter(
            role_id=user.role_id,
            feature=self.feature,
            action=self.action,
        ).exists()
