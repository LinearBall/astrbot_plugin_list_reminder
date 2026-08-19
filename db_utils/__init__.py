from typing import List

from .db_types import Todo, User, EditTodoPayload
from .dbm import DBManager
from .tag_db import TagDB
from .todo_db import TodoDB
from .user_db import UserDB


def create_todos_for_tag_users(
    tag: str,
    content: str,
    due_time: float,
    todo_db: "TodoDB",
    user_db: "UserDB",
    tag_db: "TagDB",
) -> List[Todo]:
    """给所有带有指定标签的用户批量创建待办。

    Args:
        tag: 标签名称。
        content: 待办内容。
        due_time: 到期时间戳。
        user_db: 用户数据库实例，用于按标签查找用户。
        tag_db: 标签数据库实例，用于给新待办打标签。

    Returns:
        创建出的待办列表。
    """
    created: List[Todo] = []
    for user in user_db.get_users_by_tag(tag):
        todo_id = todo_db.add_todo(user.sender_id, user.umo, content, due_time)
        tag_db.attach_tag_to_todo(todo_id, tag)
        todo = todo_db.get_todo_by_id(todo_id)
        assert todo is not None
        created.append(todo)
    return created


__all__ = [
    "Todo",
    "EditTodoPayload",
    "User",
    "DBManager",
    "TodoDB",
    "UserDB",
    "TagDB",
    "create_todos_for_tag_users",
]
