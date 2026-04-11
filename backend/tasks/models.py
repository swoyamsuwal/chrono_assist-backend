# ===============================================================
#  tasks/models.py
#  Single model: Task
#  Represents a work item on a Kanban-style board with three statuses:
#   TASK → IN_PROGRESS → FINISHED
#
#  Tenant isolation: every task is scoped to a company via follow_group
#  Two user FKs: assigned_to (who does it) and created_by (who made it)
#  PROTECT on both FKs → deleting a user is blocked if they own any tasks
# ===============================================================


# ---------------- Step 0: Imports ----------------
from django.conf import settings
from django.db import models


# ================================================================
#  Model: Task
#  Core unit of the task management board
#  Board view groups tasks by status into three columns
# ================================================================
class Task(models.Model):

    # ---------------- Step 1: Status Choices ----------------
    # Three-state lifecycle matching a Kanban board layout
    # TASK → the default state when a task is first created
    # IN_PROGRESS → task has been picked up and is being worked on
    # FINISHED → task is complete
    # Only TASK-status tasks can be deleted (enforced in the delete view)
    class Status(models.TextChoices):
        TASK        = "TASK",        "Task"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        FINISHED    = "FINISHED",    "Finished"

    # ---------------- Step 2: Tenant Isolation ----------------
    # follow_group mirrors the group_id pattern used across all apps
    # Scopes this task to one company so cross-company tasks are impossible
    # db_index=True → all board queries filter by follow_group first
    follow_group = models.PositiveIntegerField(db_index=True)

    # ---------------- Step 3: Task Content ----------------
    title             = models.CharField(max_length=255)   # Short display name shown on the board card
    short_description = models.CharField(max_length=500)   # Summary shown on the card preview
    full_description  = models.TextField()                  # Full detail shown when a task is opened
    deadline          = models.DateTimeField()              # Due date/time for the task

    # ---------------- Step 4: Assignment ----------------
    # assigned_to → the user responsible for completing this task
    # PROTECT → prevents deleting a user who still has tasks assigned to them
    # related_name="assigned_tasks" → user.assigned_tasks.all() returns their task queue
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_tasks",
    )

    # ---------------- Step 5: Status Field ----------------
    # Default is TASK → all new tasks start in the backlog column
    # db_index=True → board view filters by status frequently, index speeds this up
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TASK,
        db_index=True,
    )

    # ---------------- Step 6: Authorship ----------------
    # created_by → the user who created this task (for ownership checks on delete)
    # PROTECT → prevents deleting a user who has created tasks (audit trail preserved)
    # related_name="created_tasks" → user.created_tasks.all() returns tasks they created
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_tasks",
    )

    # ---------------- Step 7: Timestamps ----------------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # Updated on every save → used for ordering

    # ---------------- Step 8: Meta / Indexing ----------------
    class Meta:
        # Default ordering: most recently updated tasks appear first on the board
        ordering = ["-updated_at"]

        # Composite index on (follow_group, status, -updated_at)
        # Covers the board view's most common query pattern:
        #   Task.objects.filter(follow_group=X, status=Y).order_by("-updated_at")
        # Without this, a table scan would be needed for every board column render
        indexes = [
            models.Index(fields=["follow_group", "status", "-updated_at"])
        ]

    def __str__(self):
        return f"[{self.status}] {self.title}"