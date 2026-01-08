# rbac/models.py
from django.db import models
from django.conf import settings

class Feature(models.TextChoices):
    FILES = "files", "Files"
    PROMPT = "prompt", "Prompt"
    MAIL = "mail", "Mail"
    TASKS = "tasks", "Tasks"

class Action(models.TextChoices):
    VIEW = "view", "View"
    CREATE = "create", "Create"   # upload, add, etc.
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"
    EXECUTE = "execute", "Execute"  # embed, send mail, etc.

class Role(models.Model):
    # group/company = main user id (your existing rule)
    group_id = models.IntegerField(db_index=True)
    name = models.CharField(max_length=50)

    class Meta:
        unique_together = ("group_id", "name")

class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="perms")
    feature = models.CharField(max_length=20, choices=Feature.choices)
    action = models.CharField(max_length=20, choices=Action.choices)

    class Meta:
        unique_together = ("role", "feature", "action")
