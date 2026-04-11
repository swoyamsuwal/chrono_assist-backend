# ===============================================================
#  mail/rbac_perms.py
#  RBAC permission classes for the mail app
#  Split into two feature namespaces:
#
#   "mail"      → one-on-one single email actions
#   "bulk_mail" → campaign management and bulk sending
#
#  This separation lets admins grant "send single emails" without
#  also granting access to bulk campaigns (and vice versa)
# ===============================================================


# ---------------- Step 0: Imports ----------------
from rbac.permissions import HasRBACPermission  # Base class that queries RolePermission table


# ================================================================
#  One-on-One Mail Permissions
#  Used on: GenerateEmailView, SendEmailView
# ================================================================

# ---------------- Step 1: View/Generate Permission ----------------
# Required to call /generate/ — lets user ask LLaMA to draft an email
class CanViewMail(HasRBACPermission):
    feature = "mail"
    action = "view"

# ---------------- Step 2: Send Permission ----------------
# Required to call /send/ — sends the drafted email to a recipient
class CanSendMail(HasRBACPermission):
    feature = "mail"
    action = "execute"


# ================================================================
#  Bulk Mail Campaign Permissions
#  Used on: Campaign CRUD + recipient management + bulk send views
# ================================================================

# ---------------- Step 3: View Campaigns ----------------
# Required to: list campaigns, view campaign detail, list recipients
class CanViewBulkMail(HasRBACPermission):
    feature = "bulk_mail"
    action  = "view"

# ---------------- Step 4: Create Campaign ----------------
# Required to: POST /campaigns/ (create new campaign)
class CanCreateBulkMail(HasRBACPermission):
    feature = "bulk_mail"
    action  = "create"

# ---------------- Step 5: Edit Campaign ----------------
# Required to: PATCH /campaigns/<pk>/ (update name/subject/body)
#              PATCH /campaigns/<pk>/recipients/<rid>/ (edit recipient name)
class CanEditBulkMail(HasRBACPermission):
    feature = "bulk_mail"
    action  = "update"

# ---------------- Step 6: Delete Campaign ----------------
# Required to: DELETE /campaigns/<pk>/ (delete campaign)
#              DELETE /campaigns/<pk>/recipients/<rid>/ (remove recipient)
class CanDeleteBulkMail(HasRBACPermission):
    feature = "bulk_mail"
    action  = "delete"

# ---------------- Step 7: Send Bulk Mail ----------------
# Required to: POST /campaigns/<pk>/send/ (trigger bulk send)
#              POST /campaigns/<pk>/recipients/ (add recipients — gated same as send)
class CanSendBulkMail(HasRBACPermission):
    feature = "bulk_mail"
    action  = "execute"