# ===============================================================
#  tasks/views.py
#  All API views for the task management board
#
#  VIEW OVERVIEW:
#   1. create_task   → POST   create a new task in the backlog (TASK status)
#   2. board         → GET    return all tasks grouped into 3 Kanban columns
#   3. retrieve_task → GET    fetch a single task by ID
#   4. update_task   → PATCH  update fields or move a task to a new status column
#   5. delete_task   → DELETE remove a task (restricted to TASK status + creator/staff)
#
#  All views:
#   - Require IsAuthenticated + a specific RBAC permission
#   - Scope queries to the requesting user's company via follow_group
#   - Use select_related() to avoid N+1 queries on FK joins
# ===============================================================


# ---------------- Step 0: Imports ----------------
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from file_upload.utils import get_group_id
from .models import Task
from .serializers import TaskCreateSerializer, TaskDetailSerializer, TaskUpdateSerializer
from .rbac_perms import CanViewTasks, CanCreateTasks, CanUpdateTasks, CanDeleteTasks


# ================================================================
#  View 1: create_task
#  POST /tasks/
#  Body: { title, short_description, full_description, deadline, assigned_to }
#  Creates a new task in TASK status for the requesting user's company
#  Returns: the full task detail (with expanded user objects)
#  Requires: IsAuthenticated + CanCreateTasks (tasks:create RBAC check)
# ================================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated, CanCreateTasks])
def create_task(request):
    # ---------------- Step 1: Validate Input ----------------
    # context={"request": request} → passed to serializer for:
    #  - same_group() check (uses request.user)
    #  - build_absolute_uri() in TaskUserMiniSerializer (avatar URL)
    s = TaskCreateSerializer(data=request.data, context={"request": request})
    if not s.is_valid():
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

    # ---------------- Step 2: Create Task ----------------
    # s.save() calls TaskCreateSerializer.create() which injects
    # follow_group, created_by, and status=TASK server-side
    task = s.save()

    # ---------------- Step 3: Return Full Detail ----------------
    # TaskDetailSerializer returns the complete task with expanded user objects
    # (assigned_to and created_by as full objects, not just IDs)
    return Response(
        TaskDetailSerializer(task, context={"request": request}).data,
        status=status.HTTP_201_CREATED,
    )


# ================================================================
#  View 2: board
#  GET /tasks/board/
#  Returns all company tasks grouped into three Kanban columns:
#   { "TASK": [...], "IN_PROGRESS": [...], "FINISHED": [...] }
#  The frontend renders each key as a separate board column
#  Requires: IsAuthenticated + CanViewTasks (tasks:view RBAC check)
# ================================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated, CanViewTasks])
def board(request):
    # ---------------- Step 1: Get Company-Scoped Queryset ----------------
    gid = get_group_id(request.user)
    # select_related("assigned_to", "created_by") → single SQL JOIN instead of
    # N+1 individual user queries when TaskDetailSerializer iterates over tasks
    qs = Task.objects.filter(follow_group=gid).select_related("assigned_to", "created_by")

    # ---------------- Step 2: Split Into Three Columns ----------------
    # Each column is a separate filtered queryset — the composite DB index on
    # (follow_group, status, -updated_at) covers all three queries efficiently
    return Response({
        "TASK": TaskDetailSerializer(
            qs.filter(status=Task.Status.TASK),
            many=True,
            context={"request": request},
        ).data,
        "IN_PROGRESS": TaskDetailSerializer(
            qs.filter(status=Task.Status.IN_PROGRESS),
            many=True,
            context={"request": request},
        ).data,
        "FINISHED": TaskDetailSerializer(
            qs.filter(status=Task.Status.FINISHED),
            many=True,
            context={"request": request},
        ).data,
    })


# ================================================================
#  View 3: retrieve_task
#  GET /tasks/<pk>/
#  Returns a single task by ID, scoped to the requesting user's company
#  follow_group=gid in the .get() → prevents fetching another company's task
#  Requires: IsAuthenticated + CanViewTasks (tasks:view RBAC check)
# ================================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated, CanViewTasks])
def retrieve_task(request, pk: int):
    # ---------------- Step 1: Fetch Task (Company-Scoped) ----------------
    gid = get_group_id(request.user)
    try:
        # follow_group=gid → ensures we can't accidentally return another company's task
        # select_related() → avoids extra queries when serializer accesses assigned_to/created_by
        task = Task.objects.select_related("assigned_to", "created_by").get(
            id=pk,
            follow_group=gid,
        )
    except Task.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    return Response(TaskDetailSerializer(task, context={"request": request}).data)


# ================================================================
#  View 4: update_task
#  PATCH /tasks/<pk>/update/  (also accepts PUT for full replacement)
#  Updates any subset of task fields, including status transitions
#
#  Status transitions work via PATCH { "status": "IN_PROGRESS" }
#  This is how the board's drag-and-drop column move is implemented on the backend
#  Requires: IsAuthenticated + CanUpdateTasks (tasks:update RBAC check)
# ================================================================
@api_view(["PATCH", "PUT"])
@permission_classes([IsAuthenticated, CanUpdateTasks])
def update_task(request, pk: int):
    # ---------------- Step 1: Fetch Task (Company-Scoped) ----------------
    gid = get_group_id(request.user)
    try:
        task = Task.objects.get(id=pk, follow_group=gid)
    except Task.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    # ---------------- Step 2: Validate Update ----------------
    # partial=True → not all fields are required (PATCH semantics)
    # Even when called with PUT, partial=True is safe here since we
    # want the same flexible behavior for both methods
    s = TaskUpdateSerializer(task, data=request.data, partial=True, context={"request": request})
    if not s.is_valid():
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

    # ---------------- Step 3: Save + Return Updated Task ----------------
    task = s.save()
    return Response(TaskDetailSerializer(task, context={"request": request}).data)


# ================================================================
#  View 5: delete_task
#  DELETE /tasks/<pk>/delete/
#  Permanently deletes a task with TWO additional guards beyond RBAC:
#
#  Guard 1 → Status check: only TASK-status tasks can be deleted
#             Tasks in IN_PROGRESS or FINISHED are considered active/archived
#             and must be moved back to TASK before deletion is allowed
#
#  Guard 2 → Ownership check: only the original creator OR staff can delete
#             Prevents other team members from deleting tasks they didn't create
#  Requires: IsAuthenticated + CanDeleteTasks (tasks:delete RBAC check)
# ================================================================
@api_view(["DELETE"])
@permission_classes([IsAuthenticated, CanDeleteTasks])
def delete_task(request, pk: int):
    # ---------------- Step 1: Fetch Task (Company-Scoped) ----------------
    gid = get_group_id(request.user)
    try:
        task = Task.objects.get(id=pk, follow_group=gid)
    except Task.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    # ---------------- Step 2: Status Guard ----------------
    # IN_PROGRESS and FINISHED tasks cannot be deleted directly
    # User must move the task back to TASK status first via update_task
    if task.status != Task.Status.TASK:
        return Response(
            {"error": "Only TASK status can be deleted"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ---------------- Step 3: Ownership Guard ----------------
    # Only the creator of the task (or staff) can delete it
    # Prevents a scenario where any team member with delete RBAC
    # can remove tasks that other members created
    if task.created_by_id != request.user.id and not request.user.is_staff:
        return Response({"error": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)

    # ---------------- Step 4: Delete ----------------
    task.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)