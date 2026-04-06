from django.db import migrations

OWNER_PERMISSIONS = [
    ("files", "view"), ("files", "create"), ("files", "update"),
    ("files", "delete"), ("files", "execute"),
    ("prompt", "view"), ("prompt", "create"), ("prompt", "update"),
    ("prompt", "delete"), ("prompt", "execute"),
    ("mail", "view"), ("mail", "create"), ("mail", "update"),
    ("mail", "delete"), ("mail", "execute"),
    ("bulk_mail", "view"), ("bulk_mail", "create"), ("bulk_mail", "update"),  
    ("bulk_mail", "delete"), ("bulk_mail", "execute"),
    ("tasks", "view"), ("tasks", "create"), ("tasks", "update"),
    ("tasks", "delete"), ("tasks", "execute"),
    ("calendar", "view"), ("calendar", "create"), ("calendar", "update"),
    ("calendar", "delete"), ("calendar", "execute"),
    ("permission", "view"), ("permission", "create"), ("permission", "update"),
    ("permission", "delete"), ("permission", "execute"),
]

def seed_owner_template(apps, schema_editor):
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")
    role, created = Role.objects.get_or_create(group_id=0, name="Owner")
    if created:
        RolePermission.objects.bulk_create([
            RolePermission(role=role, feature=feature, action=action)
            for feature, action in OWNER_PERMISSIONS
        ])

def reverse_seed(apps, schema_editor):
    Role = apps.get_model("rbac", "Role")
    Role.objects.filter(group_id=0, name="Owner").delete()

class Migration(migrations.Migration):

    dependencies = [
        ('rbac', '0002_alter_rolepermission_feature'),
    ]

    operations = [
        migrations.RunPython(seed_owner_template, reverse_seed),
    ]