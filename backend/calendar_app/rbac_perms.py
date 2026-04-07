from rbac.permissions import HasRBACPermission

class CanConnectGoogleCalendar(HasRBACPermission):
    feature = "calendar"
    action = "view"

class CanSendCalendarPrompt(HasRBACPermission):
    feature = "calendar"
    action = "execute"
    
class CanViewCalendarPrompt(HasRBACPermission):
    feature = "calendar"
    action = "view"

