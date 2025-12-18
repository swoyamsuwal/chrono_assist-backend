# authapp/models.py (where your User model is)

from django.contrib.auth.models import AbstractUser
from django.db import models
from storages.backends.s3boto3 import S3Boto3Storage

s3_storage = S3Boto3Storage()

class User(AbstractUser):
    metadata = models.JSONField(null=True, blank=True, default=dict)

    # stored in MinIO, just like Document.file
    profile_picture = models.FileField(
        upload_to="profile_pics/",      # folder in MinIO bucket
        storage=s3_storage,
        null=True,
        blank=True,
    )