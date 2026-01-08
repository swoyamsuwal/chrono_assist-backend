# fileupload/rbac_perms.py
from rbac.permissions import HasRBACPermission

class CanViewFiles(HasRBACPermission):
    feature = "files"
    action = "view"

class CanUploadFiles(HasRBACPermission):
    feature = "files"
    action = "create"

class CanDeleteFiles(HasRBACPermission):
    feature = "files"
    action = "delete"

class CanEmbedFiles(HasRBACPermission):
    feature = "files"
    action = "execute"

class CanRagChat(HasRBACPermission):
    feature = "prompt"
    action = "execute"
