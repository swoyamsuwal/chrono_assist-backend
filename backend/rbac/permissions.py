# ===============================================================
#  rbac/permissions.py
#  The core RBAC permission check used by every app in the system
#
#  HasRBACPermission is a base class — never used directly.
#  Each app creates subclasses that set feature= and action=:
#
#    class CanViewMail(HasRBACPermission):
#        feature = "mail"
#        action  = "view"
#
#  Django REST Framework calls has_permission() on every request.
#  The method checks, in order:
#   1. Is the user a MAIN user? → allow everything
#   2. Does the user have a role assigned?
#   3. Is the user's role in the same company as the user?
#   4. Does a matching RolePermission row exist?
# ===============================================================


# ---------------- Step 0: Imports ----------------
from rest_framework.permissions import BasePermission  # DRF base class for all permission checks
from authapp.utils import get_group_id                 # Resolves the user's company group_id
from .models import RolePermission                     # The permission grant table


# ================================================================
#  Class: HasRBACPermission
#  Abstract base class — subclasses must define feature and action
#  DRF calls has_permission(request, view) before running any view method
# ================================================================
class HasRBACPermission(BasePermission):

    # ---------------- Step 1: Subclass Contract ----------------
    # Every subclass must override these two class attributes
    # If a subclass forgets, the filter() call below will match nothing → deny
    feature = None  # e.g., "mail", "calendar", "files"
    action  = None  # e.g., "view", "create", "execute"

    def has_permission(self, request, view):
        user = request.user

        # ---------------- Step 2: MAIN User Bypass ----------------
        # MAIN users are the account owner/company admin
        # They own the system and bypass all RBAC checks entirely
        # getattr() is used instead of user.user_type to avoid AttributeError
        # if the user model doesn't have this field (e.g., AnonymousUser)
        if getattr(user, "user_type", None) == "main":
            return True

        # ---------------- Step 3: Role Assignment Check ----------------
        # A user with no assigned role has zero permissions
        # role_id check avoids a DB query for the most common deny case
        if not user.role_id:
            return False

        # ---------------- Step 4: Cross-Company Tamper Check ----------------
        # Ensures the user's assigned role belongs to their own company
        # Prevents a scenario where a role from company A is somehow
        # assigned to a user in company B (data integrity guard)
        group_id = get_group_id(user)
        if user.role.group_id != group_id:
            return False

        # ---------------- Step 5: Permission Row Lookup ----------------
        # The actual RBAC check — does a matching grant row exist?
        # If a RolePermission row (role, feature, action) exists → allow
        # If no row exists → deny (default-deny architecture)
        return RolePermission.objects.filter(
            role_id=user.role_id,
            feature=self.feature,
            action=self.action,
        ).exists()