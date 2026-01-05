# documents/utils.py

def get_group_id(user) -> int:
    """
    Group rule:
    - MAIN user: follow_user is NULL -> group_id = user.id
    - SUB user: follow_user points to MAIN -> group_id = follow_user_id
    """
    return user.follow_user_id or user.id
