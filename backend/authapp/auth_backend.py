# ===============================================================
#  authapp/auth_backend.py
#  Custom authentication backend for Django
#
#  PURPOSE:
#  Django's default ModelBackend authenticates using "username + password"
#  This backend overrides that to allow "email + password" login instead
#  It is referenced as 'authapp.auth_backend.EmailAuthBackend' in:
#    - login() calls inside views.py
#    - AUTHENTICATION_BACKENDS setting in settings.py
# ===============================================================


# ---------------- Step 0: Imports ----------------
from django.contrib.auth.backends import ModelBackend  # Base class that handles password checking and user permissions
from django.contrib.auth import get_user_model          # Always use this instead of importing User directly


User = get_user_model()  # Resolves to our custom User model defined in authapp/models.py


# ================================================================
#  Class: EmailAuthBackend
#  Extends Django's built-in ModelBackend
#  Overrides only authenticate() — all other methods (get_user,
#  has_perm, etc.) are inherited from ModelBackend unchanged
# ================================================================
class EmailAuthBackend(ModelBackend):

    # ================================================================
    #  Method: authenticate
    #  Called by Django's authenticate() function in views.py
    #  Returns the User object if credentials are valid, None otherwise
    #
    #  Why two lookup paths (email vs username)?
    #  Django's authenticate() signature passes credentials as keyword
    #  args. Some internal Django calls pass "username=..." even when
    #  the field is actually an email. We handle both cases here so
    #  this backend works whether the caller sends email= or username=.
    # ================================================================
    def authenticate(self, request, username=None, email=None, password=None, **kwargs):

        # ---------------- Step 1: Look Up User by Email ----------------
        if email:
            # Caller explicitly passed email= (our login_api does this)
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                return None  # No user found with that email → deny

        else:
            # ---------------- Step 2: Fallback — Treat username as Email ----------------
            # Some Django internals (like the admin panel) pass username= instead of email=
            # We treat whatever was passed as username as if it were an email
            try:
                user = User.objects.get(email=username)
            except User.DoesNotExist:
                return None  # Still not found → deny

        # ---------------- Step 3: Verify Password ----------------
        # check_password() hashes the plain-text input and compares it
        # to the stored PBKDF2 hash — never compares plain text directly
        if user.check_password(password):
            return user  #  Credentials valid → return the user object

        # ---------------- Step 4: Password Mismatch ----------------
        # User exists but password is wrong → return None (not an exception)
        # Django's authenticate() will treat None as "backend rejected this user"
        return None