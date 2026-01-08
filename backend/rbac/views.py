from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from authapp.utils import get_group_id  # <-- this exists in YOUR authapp/utils.py now
from .models import Role
from .serializers import RoleSerializer, RoleCreateUpdateSerializer


class IsMainUserRBAC:
    def _ensure_main(self, request):
        if getattr(request.user, "user_type", None) != "main":
            return Response(
                {"error": "Only MAIN user can manage roles."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None


class RoleViewSet(IsMainUserRBAC, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        group_id = get_group_id(self.request.user)
        return Role.objects.filter(group_id=group_id).prefetch_related("perms")

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return RoleCreateUpdateSerializer
        return RoleSerializer

    def list(self, request, *args, **kwargs):
        deny = self._ensure_main(request)
        if deny:
            return deny
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        deny = self._ensure_main(request)
        if deny:
            return deny
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        deny = self._ensure_main(request)
        if deny:
            return deny
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        deny = self._ensure_main(request)
        if deny:
            return deny
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        deny = self._ensure_main(request)
        if deny:
            return deny
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        deny = self._ensure_main(request)
        if deny:
            return deny
        return super().destroy(request, *args, **kwargs)
