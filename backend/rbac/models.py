# ===============================================================
#  rbac/models.py
#  Foundation of the entire permission system
#  Three building blocks:
#
#  Feature  → TextChoices enum of every app module (files, mail, calendar, etc.)
#  Action   → TextChoices enum of every operation type (view, create, delete, etc.)
#  Role     → A named permission group scoped to one company (group_id)
#  RolePermission → A single (feature + action) grant attached to a Role
#
#  HOW IT FITS TOGETHER:
#   User → has one Role → Role has many RolePermissions
#   Each RolePermission says: "this role can perform <action> on <feature>"
#   HasRBACPermission.has_permission() checks if a matching row exists
# ===============================================================


# ---------------- Step 0: Imports ----------------
from django.db import models
from django.conf import settings


# ================================================================
#  Enum 1: Feature
#  Every app module that has RBAC-gated endpoints
#  Adding a new module here automatically makes it available as a
#  valid feature key in RolePermission and in all rbac_perms.py files
# ================================================================
class Feature(models.TextChoices):
    FILES      = "files",      "Files"
    PROMPT     = "prompt",     "Prompt"
    MAIL       = "mail",       "Mail"
    BULK_MAIL  = "bulk_mail",  "Bulk Mail"
    TASKS      = "tasks",      "Tasks"
    CALENDAR   = "calendar",   "Calendar"
    PERMISSION = "permission", "Permission"  # Controls who can manage roles themselves


# ================================================================
#  Enum 2: Action
#  The type of operation being performed on a feature
#  EXECUTE is a catch-all for non-CRUD actions like sending mail,
#  running AI prompts, triggering a bulk operation, etc.
# ================================================================
class Action(models.TextChoices):
    VIEW    = "view",    "View"     # Read access — list, retrieve
    CREATE  = "create",  "Create"   # Write new records — upload, add
    UPDATE  = "update",  "Update"   # Edit existing records
    DELETE  = "delete",  "Delete"   # Remove records
    EXECUTE = "execute", "Execute"  # Trigger actions — send mail, run AI, etc.


# ================================================================
#  Model 1: Role
#  A named permission group that belongs to one company (group_id)
#  Users are assigned a Role; their permissions come from the Role's RolePermissions
#
#  group_id → matches the MAIN user's ID for that company (tenant isolation key)
#  unique_together → no two roles in the same company can share a name
#                    (e.g., two "Admin" roles in company #5 would be ambiguous)
# ================================================================
class Role(models.Model):
    group_id = models.IntegerField(db_index=True)       # Scopes this role to one company
    name     = models.CharField(max_length=50)           # e.g., "Admin", "Viewer", "Editor"

    class Meta:
        unique_together = ("group_id", "name")           # No duplicate role names per company

    def __str__(self):
        return f"{self.name} (group {self.group_id})"


# ================================================================
#  Model 2: RolePermission
#  A single permission grant: "Role X can perform Action Y on Feature Z"
#  Multiple RolePermissions combine to form a role's full access profile
#
#  CASCADE → deleting a Role removes all its permission rows automatically
#  unique_together → prevents granting the same (role, feature, action) twice
#                    (would create ambiguous duplicate permission checks)
# ================================================================
class RolePermission(models.Model):
    role    = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="perms")
    feature = models.CharField(max_length=20, choices=Feature.choices)
    action  = models.CharField(max_length=20, choices=Action.choices)

    class Meta:
        unique_together = ("role", "feature", "action")  # One grant per (role, feature, action) combo

    def __str__(self):
        return f"{self.role.name}: {self.feature}:{self.action}"