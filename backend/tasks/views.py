from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from file_upload.utils import get_group_id
from .models import Task
from .serializers import TaskCreateSerializer, TaskDetailSerializer, TaskUpdateSerializer
from .rbac_perms import CanViewTasks, CanCreateTasks, CanUpdateTasks, CanDeleteTasks


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanCreateTasks])
def create_task(request):
    s = TaskCreateSerializer(data=request.data, context={"request": request})
    if not s.is_valid():
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

    task = s.save()
    return Response(TaskDetailSerializer(task, context={"request": request}).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated, CanViewTasks])
def board(request):
    gid = get_group_id(request.user)
    qs = Task.objects.filter(follow_group=gid).select_related("assigned_to", "created_by")

    return Response({
        "TASK": TaskDetailSerializer(qs.filter(status=Task.Status.TASK), many=True, context={"request": request}).data,
        "IN_PROGRESS": TaskDetailSerializer(qs.filter(status=Task.Status.IN_PROGRESS), many=True, context={"request": request}).data,
        "FINISHED": TaskDetailSerializer(qs.filter(status=Task.Status.FINISHED), many=True, context={"request": request}).data,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, CanViewTasks])
def retrieve_task(request, pk: int):
    gid = get_group_id(request.user)
    try:
        task = Task.objects.select_related("assigned_to", "created_by").get(id=pk, follow_group=gid)
    except Task.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    return Response(TaskDetailSerializer(task, context={"request": request}).data)


@api_view(["PATCH", "PUT"])
@permission_classes([IsAuthenticated, CanUpdateTasks])
def update_task(request, pk: int):
    gid = get_group_id(request.user)
    try:
        task = Task.objects.get(id=pk, follow_group=gid)
    except Task.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    s = TaskUpdateSerializer(task, data=request.data, partial=True, context={"request": request})
    if not s.is_valid():
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

    task = s.save()
    return Response(TaskDetailSerializer(task, context={"request": request}).data)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated, CanDeleteTasks])
def delete_task(request, pk: int):
    gid = get_group_id(request.user)
    try:
        task = Task.objects.get(id=pk, follow_group=gid)
    except Task.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    if task.status != Task.Status.TASK:
        return Response({"error": "Only TASK status can be deleted"}, status=status.HTTP_400_BAD_REQUEST)

    if task.created_by_id != request.user.id and not request.user.is_staff:
        return Response({"error": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)

    task.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
