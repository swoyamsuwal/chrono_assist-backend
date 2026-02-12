from rbac.permissions import HasRBACPermission

class CanConnectGoogleCalendar(HasRBACPermission):
    feature = "calendar"
    action = "execute"

class CanSendCalendarPrompt(HasRBACPermission):
    feature = "calendar"
    action = "execute"
