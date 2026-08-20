from typing import List

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

    def remove_tag_from_todo(self, todo_id: int, tag: str) -> bool:
        """Remove a tag from a todo.

        Args:
            todo_id: Todo ID.
            tag: Tag name.

        Returns:
            Whether the association was removed.
        """
        with self.dbm.get_conn() as conn:
            cur = conn.execute(
                """DELETE FROM TodoTags
                WHERE todo_id = ? AND tag_id IN (SELECT tag_id FROM Tags WHERE name = ?)""",
                (todo_id, tag),
            )
            return cur.rowcount > 0

    def get_user_tags(self, sender_id: str) -> List[str]:
        """查询指定用户的全部标签。

        Args:
            sender_id: 用户 sender_id。

        Returns:
            标签名列表。
        """
        with self.dbm.get_conn() as conn:
            rows = conn.execute(
                """SELECT t.name FROM Tags t
                JOIN UserTags ut ON ut.tag_id = t.tag_id
                WHERE ut.sender_id = ? ORDER BY t.name""",
                (sender_id,),
            ).fetchall()
        return [row[0] for row in rows]

    def remove_tag_from_user(self, sender_id: str, tag: str) -> bool:
        """移除用户身上的某个标签。

        Args:
            sender_id: 用户 sender_id。
            tag: 标签名称。

        Returns:
            是否删除了关联。
        """
        with self.dbm.get_conn() as conn:
            cur = conn.execute(
                """DELETE FROM UserTags
                WHERE sender_id = ? AND tag_id IN (SELECT tag_id FROM Tags WHERE name = ?)""",
                (sender_id, tag),
            )
            return cur.rowcount > 0
