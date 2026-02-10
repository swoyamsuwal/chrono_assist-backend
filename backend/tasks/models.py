from django.conf import settings
from django.db import models

class Task(models.Model):
    class Status(models.TextChoices):
        TASK = "TASK", "Task"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        FINISHED = "FINISHED", "Finished"

    follow_group = models.PositiveIntegerField(db_index=True)

    title = models.CharField(max_length=255)
    short_description = models.CharField(max_length=500)
    full_description = models.TextField()
    deadline = models.DateTimeField()

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_tasks",
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TASK, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_tasks",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["follow_group", "status", "-updated_at"])]
