# ===============================================================
#  authapp/models.py
#  Defines the custom User model that extends Django's AbstractUser
#  This is the foundation — every other part of authapp depends on this
# ===============================================================


# ---------------- Step 0: Imports ----------------
from django.contrib.auth.models import AbstractUser  # Base class with built-in auth fields (username, password, etc.)
from django.db import models
from storages.backends.s3boto3 import S3Boto3Storage  # MinIO/S3 storage backend for file uploads


# ---------------- Step 1: Storage Backend ----------------
# s3_storage tells Django to use MinIO (S3-compatible) instead of local disk
# This is reused for profile_picture field below
s3_storage = S3Boto3Storage()


# ---------------- Step 2: Custom User Model ----------------
class User(AbstractUser):

    # ---------------- Step 2a: User Type Enum ----------------
    # Defines two kinds of users in the system:
    # MAIN  → the owner/admin of a company (registers themselves)
    # SUB   → a staff member created by a MAIN user
    class UserType(models.TextChoices):
        MAIN = 'main', 'Main'
        SUB = 'sub', 'Sub'

    # ---------------- Step 2b: Metadata Field ----------------
    # JSON blob to store flexible data that doesn't need its own DB column
    # Currently used to store OTP info (code, expiry, attempts, is_used)
    metadata = models.JSONField(null=True, blank=True, default=dict)

    # ---------------- Step 2c: Profile Picture ----------------
    # Stored in MinIO bucket under "profile_pics/" folder
    # Uses s3_storage so it behaves like a normal FileField but writes to MinIO
    profile_picture = models.FileField(
        upload_to="profile_pics/",
        storage=s3_storage,
        null=True,
        blank=True,
    )

    # ---------------- Step 2d: User Type Field ----------------
    # Tracks whether this user is MAIN (owner) or SUB (staff)
    # Defaults to MAIN so self-registration always creates an owner
    user_type = models.CharField(
        max_length=4,
        choices=UserType.choices,
        default=UserType.MAIN,
    )

    # ---------------- Step 2e: Follow User (Company Grouping) ----------------
    # Self-referencing FK used to group users under the same "company"
    # MAIN user → follow_user points to themselves (set during register)
    # SUB user  → follow_user points to their MAIN user (set during sub-register)
    # This is how the system knows "which company does this user belong to?"
    follow_user = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='followers',
    )

    # ---------------- Step 2f: Role FK ----------------
    # Links to the RBAC Role model so this user inherits permissions from their role
    # MAIN users get an auto-created "Owner" role during registration
    # SUB users get a role assigned by the MAIN user at creation time
    role = models.ForeignKey(
        "rbac.Role",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="users"
    )

    # ---------------- Step 2g: Unique Email ----------------
    # Overrides AbstractUser's email field to enforce uniqueness
    # Login is done by email (not username), so this must be unique
    email = models.EmailField(unique=True)