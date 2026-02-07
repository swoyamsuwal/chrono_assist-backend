from django.db import models
from django.utils import timezone
import jsonfield  # optional but plain TextField works

class GoogleCredentials(models.Model):
    """
    Stores Google credentials JSON for a single user (dev example).
    In production, tie this to your User model, encrypt tokens, handle refresh.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    credentials_json = models.TextField(blank=True, default="")  # store google oauth2 credentials as JSON

    def __str__(self):
        return f"GoogleCredentials({self.id})"
