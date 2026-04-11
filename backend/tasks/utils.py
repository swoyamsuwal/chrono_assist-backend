# ===============================================================
#  tasks/utils.py
#  Small utility used by serializers to enforce cross-company assignment rules
#
#  same_group() → checks if two users belong to the same company
#  Used in: TaskCreateSerializer and TaskUpdateSerializer to validate
#  that assigned_to must be from the same company as the requesting user
# ===============================================================


# ---------------- Step 0: Imports ----------------
from file_upload.utils import get_group_id  # Resolves a user's company group_id


# ================================================================
#  Function: same_group
#  Returns True if both users share the same group_id (same company)
#  Used as a cross-company guard in assignment validation:
#   "You cannot assign a task to someone from another company"
#
#  Why needed? Without this check, a user could assign tasks to users
#  from other companies — leaking their task context cross-tenant
# ================================================================
def same_group(user1, user2) -> bool:
    return get_group_id(user1) == get_group_id(user2)