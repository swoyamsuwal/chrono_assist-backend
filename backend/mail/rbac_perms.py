# mail/rbac_perms.py
# ── One-on-one Mail ──────────────────────────
from rbac.permissions import HasRBACPermission

class CanViewMail(HasRBACPermission):
    feature = "mail"
    action = "view"

class CanSendMail(HasRBACPermission):
    feature = "mail"
    action = "execute"

# ── Bulk Mail Campaign ───────────────────────
class CanViewBulkMail(HasRBACPermission):
    feature = "bulk_mail"
    action  = "view"

class CanCreateBulkMail(HasRBACPermission):
    feature = "bulk_mail"
    action  = "create"

class CanEditBulkMail(HasRBACPermission):
    feature = "bulk_mail"
    action  = "update"

class CanDeleteBulkMail(HasRBACPermission):
    feature = "bulk_mail"
    action  = "delete"

class CanSendBulkMail(HasRBACPermission):
    feature = "bulk_mail"
    action  = "execute"
