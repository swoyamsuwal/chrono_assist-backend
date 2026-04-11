# ===============================================================
#  rbac/rbac_perms.py
#  RBAC permission classes for the role management module itself
#  Controls who can view, create, update, and delete roles
#
#  All classes use feature="permission" — this is the meta-permission
#  that gates access to the RBAC management UI itself
#
#  Typical setup:
#   - MAIN users → always bypass (HasRBACPermission logic)
#   - Company admins → granted permission:view + permission:create etc.
#   - Regular users → no permission grants → cannot access role management
# ===============================================================


# ---------------- Step 0: Imports ----------------
from rbac.permissions import HasRBACPermission  # Base class for all RBAC checks


# ================================================================
#  Permission Classes — feature="permission"
#  Each class maps to one action on the role management module
# ================================================================

# ---------------- Step 1: View Roles ----------------
# Required for: GET /rbac/roles/ and GET /rbac/roles/<id>/
# Base gate — all role management access starts here
class CanViewPermissionModule(HasRBACPermission):
    feature = "permission"
    action = "view"

# ---------------- Step 2: Create Role ----------------
# Required for: POST /rbac/roles/ (creating a new role with permissions)
class CanCreateRole(HasRBACPermission):
    feature = "permission"
    action = "create"

# ---------------- Step 3: Update Role ----------------
# Required for: PATCH /rbac/roles/<id>/ (renaming or updating permissions on a role)
class CanUpdateRole(HasRBACPermission):
    feature = "permission"
    action = "update"

# ---------------- Step 4: Delete Role ----------------
# Required for: DELETE /rbac/roles/<id>/ (removing a role and all its permission grants)
class CanDeleteRole(HasRBACPermission):
    feature = "permission"
    action = "delete"