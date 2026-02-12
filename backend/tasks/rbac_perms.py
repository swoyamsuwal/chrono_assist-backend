# tasks/rbac_perms.py
from rbac.permissions import HasRBACPermission

class CanViewTasks(HasRBACPermission):
    feature = "tasks"
    action = "view"

class CanCreateTasks(HasRBACPermission):
    feature = "tasks"
    action = "create"

class CanUpdateTasks(HasRBACPermission):
    feature = "tasks"
    action = "update"

class CanDeleteTasks(HasRBACPermission):
    feature = "tasks"
    action = "delete"
