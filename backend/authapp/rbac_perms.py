# ===============================================================
#  authapp/rbac_perms.py
#  Defines DRF permission classes specific to the authapp module
#  Each class maps to a feature+action pair checked against the user's role
#  These are used as @permission_classes([...]) guards on views
# ===============================================================


# ---------------- Step 0: Imports ----------------
from rbac.permissions import HasRBACPermission  # Base class that does the actual DB permission check


# ================================================================
#  All four classes below follow the same pattern:
#  They inherit HasRBACPermission and declare:
#    feature = "permission"  → the module being protected (user management)
#    action  = "view/create/update/delete"  → the operation being performed
#
#  HasRBACPermission.has_permission() will look up RolePermission rows
#  matching (user.role_id, feature, action) to allow or deny access
# ================================================================


# ---------------- Step 1: View Permission ----------------
# Guards any view that lists or reads user data
# Required for: list_users_api
class CanViewPermissionModule(HasRBACPermission):
    feature = "permission"
    action = "view"


# ---------------- Step 2: Create Permission ----------------
# Guards any view that creates new sub-users
# Required for: sub_register_api
class CanCreateAccount(HasRBACPermission):
    feature = "permission"
    action = "create"


# ---------------- Step 3: Update Permission ----------------
# Guards any view that modifies existing user data
# Required for: update_user_role_api
class CanUpdateAccount(HasRBACPermission):
    feature = "permission"
    action = "update"


# ---------------- Step 4: Delete Permission ----------------
# Guards any view that removes users from the system
# Required for: delete_user_api
class CanDeleteAccount(HasRBACPermission):
    feature = "permission"
    action = "delete"