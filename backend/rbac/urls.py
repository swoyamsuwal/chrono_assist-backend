# ===============================================================
#  rbac/urls.py
#  Uses DRF's DefaultRouter to auto-generate all RESTful URLs
#  for the RoleViewSet — no manual path() entries needed
#
#  Routes registered by DefaultRouter for "roles":
#   GET    /rbac/roles/        → RoleViewSet.list()
#   POST   /rbac/roles/        → RoleViewSet.create()
#   GET    /rbac/roles/<id>/   → RoleViewSet.retrieve()
#   PATCH  /rbac/roles/<id>/   → RoleViewSet.partial_update()
#   PUT    /rbac/roles/<id>/   → RoleViewSet.update()
#   DELETE /rbac/roles/<id>/   → RoleViewSet.destroy()
#
#  Mounted under /api/rbac/ in backend/urls.py
# ===============================================================


# ---------------- Step 0: Imports ----------------
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RoleViewSet


# ---------------- Step 1: Register ViewSet with Router ----------------
# basename="roles" → used to name the auto-generated URL patterns
# e.g., "roles-list", "roles-detail" (used in reverse() and testing)
router = DefaultRouter()
router.register(r"roles", RoleViewSet, basename="roles")


# ---------------- Step 2: Expose Router URLs ----------------
# include(router.urls) expands to all six RESTful routes above
urlpatterns = [
    path("", include(router.urls)),
]