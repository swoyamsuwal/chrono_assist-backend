# ===============================================================
#  tasks/urls.py
#  URL routing for all task management endpoints
#  Mounted under /api/ in backend/urls.py
#
#  DESIGN NOTE: Explicit paths are used instead of a ViewSet + Router
#  because each action has meaningfully different permission requirements
#  and the explicit names make the intent of each URL obvious
# ===============================================================


# ---------------- Step 0: Imports ----------------
from django.urls import path
from . import views


urlpatterns = [

    # ---------------- Step 1: Task Creation ----------------
    # POST → creates a new task in TASK status for the requesting user's company
    path("tasks/", views.create_task),

    # ---------------- Step 2: Kanban Board ----------------
    # GET → returns all company tasks grouped into TASK / IN_PROGRESS / FINISHED columns
    # NOTE: "tasks/board/" must come BEFORE "tasks/<int:pk>/" in the URL list
    # Otherwise Django would try to match "board" as a <pk> integer and fail
    path("tasks/board/", views.board),

    # ---------------- Step 3: Single Task Operations ----------------
    # GET → retrieve one task by ID (company-scoped)
    path("tasks/<int:pk>/", views.retrieve_task),

    # PATCH/PUT → update fields or change the task's status column
    path("tasks/<int:pk>/update/", views.update_task),

    # DELETE → remove a task (TASK status only, creator/staff only)
    path("tasks/<int:pk>/delete/", views.delete_task),
]