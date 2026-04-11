# ===============================================================
#  file_upload/rbac_perms.py
#  RBAC permission classes for the file_upload module
#  Each class maps to a specific feature + action combination
#  Used as @permission_classes([IsAuthenticated, CanXxx]) guards on views
# ===============================================================


# ---------------- Step 0: Imports ----------------
from rbac.permissions import HasRBACPermission  # Base class that queries RolePermission table


# ================================================================
#  All classes below follow the same pattern:
#   feature = the module being protected ("files" or "prompt")
#   action  = the operation being gated ("view", "create", "delete", "execute")
#
#  HasRBACPermission checks: does user.role have a RolePermission row
#  matching (feature, action)? If yes → allow. If no → 403.
#  MAIN users bypass all checks (they own the system).
# ================================================================


# ---------------- Step 1: File Read Permission ----------------
# Required to call list_files — see/list documents in the company group
class CanViewFiles(HasRBACPermission):
    feature = "files"
    action = "view"


# ---------------- Step 2: File Upload Permission ----------------
# Required to call upload_file — add new documents to the company group
class CanUploadFiles(HasRBACPermission):
    feature = "files"
    action = "create"


# ---------------- Step 3: File Delete Permission ----------------
# Required to call delete_file — remove documents (only own files)
class CanDeleteFiles(HasRBACPermission):
    feature = "files"
    action = "delete"


# ---------------- Step 4: Embed Permission ----------------
# Required to call embed_file — trigger the embedding pipeline on a document
# Uses action "execute" since embedding is a processing action, not a CRUD operation
class CanEmbedFiles(HasRBACPermission):
    feature = "files"
    action = "execute"


# ---------------- Step 5: RAG Chat Permission ----------------
# Required to call rag_chat and doc_chat
# Scoped under "prompt" feature since it's an AI query action, not file management
class CanRagChat(HasRBACPermission):
    feature = "prompt"
    action = "execute"