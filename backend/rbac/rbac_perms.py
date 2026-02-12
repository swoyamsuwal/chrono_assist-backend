from rbac.permissions import HasRBACPermission

class CanViewPermissionModule(HasRBACPermission):
    feature = "permission"
    action = "view"

class CanCreateRole(HasRBACPermission):
    feature = "permission"
    action = "create"

class CanUpdateRole(HasRBACPermission):
    feature = "permission"
    action = "update"

class CanDeleteRole(HasRBACPermission):
    feature = "permission"
    action = "delete"
