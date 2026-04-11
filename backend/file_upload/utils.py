# ===============================================================
#  file_upload/utils.py
#  Shared helper used across views, serializers, and embedding pipeline
#  Mirrors the same function in authapp/utils.py — kept here so
#  file_upload has no cross-app import dependency on authapp
# ===============================================================


# ================================================================
#  Helper: get_group_id
#  Resolves the "company namespace" for any user
#
#  Rule:
#   MAIN user → follow_user is NULL → group_id = user.id (they ARE the root)
#   SUB user  → follow_user points to their MAIN → group_id = follow_user_id
#
#  Why this matters:
#   All DB queries in file_upload are scoped by follow_group=group_id
#   This ensures MAIN and all their SUB users share the same pool of documents
#   and a SUB user can never see another company's files
# ================================================================
def get_group_id(user) -> int:
    return user.follow_user_id or user.id