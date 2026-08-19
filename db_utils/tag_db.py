from .dbm import DBManager


class TagDB:
    """标签数据库：管理标签及标签与用户/待办的关联。复用 TodoDB 的连接。"""

    def __init__(self, dbm: DBManager) -> None:
        self.dbm = dbm

    def get_or_create_tag(self, name: str) -> int:
        """按名称获取标签 ID，标签不存在时先创建。

        Args:
            name: 标签名称。

        Returns:
            标签 ID。

        Raises:
            ValueError: 标签名为空时。
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("标签名不能为空")
        with self.dbm.get_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO Tags (name) VALUES (?)", (name,))
            row = conn.execute(
                "SELECT tag_id FROM Tags WHERE name = ?", (name,)
            ).fetchone()
        return row[0]

    def attach_tag_to_user(self, sender_id: str, tag: str) -> None:
        """给用户附加一个标签。

        Args:
            sender_id: 用户唯一标识。
            tag: 标签名称。
        """
        tag_id = self.get_or_create_tag(tag)
        with self.dbm.get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO UserTags (sender_id, tag_id) VALUES (?, ?)",
                (sender_id, tag_id),
            )

    def attach_tag_to_todo(self, todo_id: int, tag: str) -> None:
        """给待办附加一个标签。

        Args:
            todo_id: 待办 ID。
            tag: 标签名称。
        """
        tag_id = self.get_or_create_tag(tag)
        with self.dbm.get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO TodoTags (todo_id, tag_id) VALUES (?, ?)",
                (todo_id, tag_id),
            )
