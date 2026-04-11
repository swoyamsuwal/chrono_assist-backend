# ===============================================================
#  calendar_app/rbac_perms.py
#  RBAC permission classes for the calendar_app module
#  Each class maps to a feature + action pair checked against the user's role
#  Used as @permission_classes([IsAuthenticated, CanXxx]) guards on views
# ===============================================================


# ---------------- Step 0: Imports ----------------
from rbac.permissions import HasRBACPermission  # Base class that queries RolePermission table


# ================================================================
#  All classes below use feature="calendar"
#  HasRBACPermission checks: does user.role have a RolePermission row
#  matching (feature="calendar", action=X)?
#  MAIN users bypass all checks automatically (they own the system).
# ================================================================


# ---------------- Step 1: Calendar Connect + View Permission ----------------
# Required for: google_login, list_events, create_event, update_event, delete_event
# "view" is used as the base gate for all calendar interactions
class CanConnectGoogleCalendar(HasRBACPermission):
    feature = "calendar"
    action = "view"


# ---------------- Step 2: AI Prompt Permission ----------------
# Required for: ai_prompt_handler
# "execute" separates AI-driven actions from manual CRUD
# Allows admins to grant AI chat access independently of raw event management
class CanSendCalendarPrompt(HasRBACPermission):
    feature = "calendar"
    action = "execute"


# ---------------- Step 3: View Calendar Prompt (Read-only AI) ----------------
# Currently unused in views but reserved for future read-only AI calendar queries
class CanViewCalendarPrompt(HasRBACPermission):
    feature = "calendar"
    action = "view"