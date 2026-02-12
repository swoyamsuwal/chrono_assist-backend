from rbac.permissions import HasRBACPermission

class CanViewPermissionModule(HasRBACPermission):
    feature = "permission"
    action = "view"

class CanCreateAccount(HasRBACPermission):
    feature = "permission"
    action = "create"

class CanUpdateAccount(HasRBACPermission):
    feature = "permission"
    action = "update"

class CanDeleteAccount(HasRBACPermission):
    feature = "permission"
    action = "delete"
