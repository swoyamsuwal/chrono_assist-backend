# ===============================================================
#  mail/models.py
#  Two models power the bulk email campaign system:
#
#  EmailCampaign      → a named group of recipients with a shared subject/body draft
#  CampaignRecipient  → a single email address belonging to a campaign
#
#  Relationship: one EmailCampaign → many CampaignRecipients
#  Tenant isolation: every campaign is scoped to a company via group_id
# ===============================================================


# ---------------- Step 0: Imports ----------------
from django.db import models
from django.conf import settings


# ================================================================
#  Model 1: EmailCampaign
#  Represents a named bulk email campaign for a specific company group
#  Stores the reusable subject + body draft that gets sent to all recipients
# ================================================================
class EmailCampaign(models.Model):

    # ---------------- Step 1a: Tenant Isolation ----------------
    # group_id mirrors the follow_group pattern from file_upload
    # Scopes the campaign to one company so no cross-company data leaks
    # db_index=True → speeds up queries that filter by group_id
    group_id = models.PositiveIntegerField(db_index=True)

    # ---------------- Step 1b: Campaign Identity ----------------
    name = models.CharField(max_length=255)  # e.g., "Q4 Newsletter", "Product Launch"

    # ---------------- Step 1c: Email Draft ----------------
    # subject and body are stored on the campaign so the user can
    # write the draft once and send it to all recipients later
    # blank/default="" → draft is optional; view validates before sending
    subject = models.CharField(max_length=500, blank=True, default="")
    body    = models.TextField(blank=True, default="")

    # ---------------- Step 1d: Ownership ----------------
    # Tracks which user created this campaign (for audit purposes)
    # CASCADE → when a user is deleted, their campaigns are also deleted
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="campaigns"
    )

    # ---------------- Step 1e: Timestamps ----------------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


# ================================================================
#  Model 2: CampaignRecipient
#  Represents ONE email address in a campaign's recipient list
#  name is auto-extracted from the email local part (e.g., john.doe@ → "John")
#  or can be manually set later via the PATCH endpoint
# ================================================================
class CampaignRecipient(models.Model):

    # ---------------- Step 2a: Parent Campaign ----------------
    # CASCADE → deleting a campaign also deletes all its recipients
    # related_name="recipients" → campaign.recipients.all() returns all recipients
    campaign = models.ForeignKey(
        EmailCampaign,
        on_delete=models.CASCADE,
        related_name="recipients"
    )

    # ---------------- Step 2b: Recipient Data ----------------
    email = models.EmailField()
    # name is shown in the "Dear {name}" greeting when sending
    # auto-populated from the email address during bulk import
    name  = models.CharField(max_length=255, blank=True)

    # ---------------- Step 2c: Uniqueness Constraint ----------------
    # Prevents the same email from being added to the same campaign twice
    # Enforced at the DB level — get_or_create() in the view also handles this gracefully
    class Meta:
        unique_together = ("campaign", "email")

    def __str__(self):
        return f"{self.name} <{self.email}>"