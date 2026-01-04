# authapp/models.py (where your User model is)

from django.contrib.auth.models import AbstractUser
from django.db import models
from storages.backends.s3boto3 import S3Boto3Storage

s3_storage = S3Boto3Storage()

class User(AbstractUser):
    class UserType(models.TextChoices):
        MAIN = 'main', 'Main'
        SUB = 'sub', 'Sub'
    metadata = models.JSONField(null=True, blank=True, default=dict)

    # stored in MinIO, just like Document.file
    profile_picture = models.FileField(
        upload_to="profile_pics/",      # folder in MinIO bucket
        storage=s3_storage,
        null=True,
        blank=True,
    )
    user_type = models.CharField(
        max_length=4,
        choices=UserType.choices,
        default=UserType.MAIN,
    )
    follow_user = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='followers',
    )