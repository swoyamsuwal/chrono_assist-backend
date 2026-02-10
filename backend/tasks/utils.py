from file_upload.utils import get_group_id

def same_group(user1, user2) -> bool:
    return get_group_id(user1) == get_group_id(user2)
