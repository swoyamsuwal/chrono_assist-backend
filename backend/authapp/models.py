from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    metadata = models.JSONField(null=True, blank=True, default=dict)
