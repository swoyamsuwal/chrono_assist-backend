# ===============================================================
#  backend/urls.py  (Root URL Configuration)
#  The single entry point that Django uses to route ALL incoming
#  HTTP requests to the correct app's urls.py
#
#  URL PREFIX MAP:
#   /admin/          → Django built-in admin panel
#   /authapp/        → Auth: register, login, OTP, profile, users
#   /file_upload/    → Files: upload, list, delete, embed, RAG chat
#   /rbac/           → Role & permission management
#   /api/mail/       → Email / mail features
#   /api/calendar/   → Google Calendar integration
#   /api/tasks/      → Task management
#   /api/token/      → JWT access token generation
#   /api/token/refresh/ → JWT access token refresh
# ===============================================================


# ---------------- Step 0: Imports ----------------
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static  # Serves MEDIA files in dev mode (not for production)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView  # JWT built-in views


urlpatterns = [

    # ---------------- Step 1: Django Admin ----------------
    # Built-in Django admin UI — accessible at /admin/
    # Only works for users with is_staff=True
    path('admin/', admin.site.urls),

    # ---------------- Step 2: Auth App ----------------
    # Handles: register, sub-register, login (step 1), OTP verify (step 2),
    #          profile GET/PUT, list users, update role, delete user, my-permissions
    path('authapp/', include('authapp.urls')),

    # ---------------- Step 3: File Upload / RAG App ----------------
    # Handles: upload, list, delete, embed, rag_chat, preview, doc_chat
    path('file_upload/', include('file_upload.urls')),

    # ---------------- Step 4: RBAC (Role-Based Access Control) ----------------
    # Handles: create/list/update/delete roles and their permission sets
    path('rbac/', include('rbac.urls')),

    # ---------------- Step 5: Mail App ----------------
    # Handles: email sending features (e.g., send, inbox, compose)
    path('api/mail/', include('mail.urls')),

    # ---------------- Step 6: Calendar App ----------------
    # Handles: Google Calendar OAuth flow and calendar event management
    path('api/calendar/', include('calendar_app.urls')),

    # ---------------- Step 7: Tasks App ----------------
    # Handles: task creation, assignment, status updates, listing
    path("api/tasks/", include("tasks.urls")),

    # ---------------- Step 8: JWT Token Endpoints ----------------
    # POST /api/token/         → send email+password → receive access + refresh tokens
    # POST /api/token/refresh/ → send refresh token  → receive new access token
    # NOTE: These are SimpleJWT built-in views — they use username+password by default.
    #       For email login in your system, the custom login_api + OTP flow is used instead.
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]


# ---------------- Step 9: Media File Serving (Development Only) ----------------
# In production, a web server (Nginx) or MinIO serves files directly.
# In development (DEBUG=True), Django itself serves files uploaded to MEDIA_ROOT.
# This line appends media URL patterns only when DEBUG is on.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)