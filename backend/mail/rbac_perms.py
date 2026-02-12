# mail/rbac_perms.py
from rbac.permissions import HasRBACPermission

class CanViewMail(HasRBACPermission):
    feature = "mail"
    action = "view"

class CanSendMail(HasRBACPermission):
    feature = "mail"
    action = "execute"
