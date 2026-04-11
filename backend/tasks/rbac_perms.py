# ===============================================================
#  tasks/rbac_perms.py
#  RBAC permission classes for the tasks module
#  All classes use feature="tasks" with the standard CRUD action set
#
#  Used as @permission_classes decorators on all task views
#  MAIN users bypass all checks automatically (HasRBACPermission logic)
# ===============================================================


# ---------------- Step 0: Imports ----------------
from rbac.permissions import HasRBACPermission  # Base class that queries RolePermission table


# ================================================================
#  Permission Classes — feature="tasks"
# ================================================================

# ---------------- Step 1: View Tasks ----------------
# Required for: GET /tasks/board/, GET /tasks/<pk>/
class CanViewTasks(HasRBACPermission):
    feature = "tasks"
    action = "view"

# ---------------- Step 2: Create Task ----------------
# Required for: POST /tasks/
class CanCreateTasks(HasRBACPermission):
    feature = "tasks"
    action = "create"

# ---------------- Step 3: Update Task ----------------
# Required for: PATCH/PUT /tasks/<pk>/update/
# Also covers status transitions (TASK → IN_PROGRESS → FINISHED)
class CanUpdateTasks(HasRBACPermission):
    feature = "tasks"
    action = "update"

# ---------------- Step 4: Delete Task ----------------
# Required for: DELETE /tasks/<pk>/delete/
# Additional guard in the view: only TASK-status tasks can be deleted,
# and only by the creator or staff
class CanDeleteTasks(HasRBACPermission):
    feature = "tasks"
    action = "delete"