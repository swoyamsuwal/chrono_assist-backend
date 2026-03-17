from django.db import models
from django.conf import settings


class EmailCampaign(models.Model):
    """A named group of recipients for bulk email sending."""
    group_id    = models.PositiveIntegerField(db_index=True)   # tenant isolation key
    name        = models.CharField(max_length=255)
    subject    = models.CharField(max_length=500, blank=True, default="")
    body       = models.TextField(blank=True, default="")
    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="campaigns"
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class CampaignRecipient(models.Model):
    """A single email recipient belonging to a campaign."""
    campaign = models.ForeignKey(
        EmailCampaign,
        on_delete=models.CASCADE,
        related_name="recipients"
    )
    email = models.EmailField()
    name  = models.CharField(max_length=255, blank=True)  # auto-extracted or manually set

    class Meta:
        unique_together = ("campaign", "email")   # no duplicate emails per campaign

    def __str__(self):
        return f"{self.name} <{self.email}>"
