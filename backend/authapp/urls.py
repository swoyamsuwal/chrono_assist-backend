# ===============================================================
#  authapp/urls.py
#  URL routing for all authentication and user management endpoints
#  These are mounted under a prefix (e.g., /api/auth/) in the root urls.py
# ===============================================================


# ---------------- Step 0: Imports ----------------
from django.urls import path
from . import views


urlpatterns = [

    # ---------------- Step 1: CSRF Setup ----------------
    # Frontend calls this first to get a CSRF cookie before any POST request
    path('csrf/', views.get_csrf, name='get_csrf'),

    # ---------------- Step 2: Main User Registration ----------------
    # Self-registration → always creates a MAIN user with an Owner role
    path('register/', views.register_api, name='register_api'),

    # ---------------- Step 3: Two-Step Login Flow ----------------
    # Step 3a → Validate email+password, then send OTP to email
    path('login/', views.login_api, name='login_api'),
    # Step 3b → Verify the OTP code, then create the session
    path('verify-otp/', views.verify_otp_api, name='verify_otp_api'),

    # ---------------- Step 4: Profile Management ----------------
    # GET → return current user's profile data
    # PUT → update username, name, profile picture
    path('profile/', views.profile_api, name='profile_api'),

    # ---------------- Step 5: Sub User Management ----------------
    # Create a SUB user under the currently logged-in MAIN user
    path('sub-register/', views.sub_register_api, name='sub_register_api'),
    # List all SUB users that belong to the current user's company
    path('list_users/', views.list_users_api, name='list_users_api'),
    # PATCH → update a specific sub-user's role or email
    path("users/<int:user_id>/role/", views.update_user_role_api, name="update_user_role"),
    # DELETE → remove a specific sub-user from the company
    path("users/<int:user_id>/", views.delete_user_api, name="delete_user"),

    # ---------------- Step 6: Permission Introspection ----------------
    # Returns the current user's permissions so the frontend can
    # show/hide UI elements based on what they're allowed to do
    path('my-permissions/', views.my_permissions, name='my-permissions'),
]