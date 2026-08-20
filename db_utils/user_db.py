from typing import List

from .db_types import User
from .dbm import DBManager


class UserDB:
    """用户数据库：管理与查询用户及其标签。"""

    def __init__(self, dbm: DBManager) -> None:
        self.dbm = dbm

    def add_or_update_user(
        self,
        sender_id: str,
        umo_of_bot: str,
        is_admin: bool = False,
        nickname: str | None = None,
    ) -> None:
        """新增或更新用户信息。

        新用户昵称默认等于 sender_id；更新时不改动已有昵称，以保留用户自定义昵称。

        Args:
            sender_id: 用户唯一标识（event.get_sender_id()）。
            umo_of_bot: 用户私聊窗口对应会话的 umo。
            is_admin: 是否有管理员权限。
            nickname: 昵称，仅在首次创建时生效，缺省为 sender_id。
        """
        nick = nickname or sender_id
        with self.dbm.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO Users (sender_id, umo_of_bot, is_admin, nickname)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(sender_id) DO UPDATE SET
                    umo_of_bot = excluded.umo_of_bot,
                    is_admin = excluded.is_admin
                """,
                (sender_id, umo_of_bot, int(is_admin), nick),
            )

    def get_user(self, sender_id: str) -> User | None:
        """按 sender_id 查询用户。

        Args:
            sender_id: 用户唯一标识。

        Returns:
            用户信息；不存在时返回 None。
        """
        with self.dbm.get_conn() as conn:
            row = conn.execute(
                "SELECT sender_id, umo_of_bot, is_admin, nickname FROM Users WHERE sender_id = ?",
                (sender_id,),
            ).fetchone()
        if row is None:
            return None
        return User.from_db_row(row)

    def get_users_by_tag(self, tag: str) -> List[User]:
        """根据标签批量查询用户。

        Args:
            tag: 标签名称。

        Returns:
            带有该标签的用户列表。
        """
        with self.dbm.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT u.sender_id, u.umo_of_bot, u.is_admin, u.nickname
                FROM Users as u
                JOIN UserTags as ut ON ut.sender_id = u.sender_id
                JOIN Tags as t ON t.tag_id = ut.tag_id
                WHERE t.name = ?
                """,
                (tag,),
            )
            rows = cursor.fetchall()
        return [User.from_db_row(row) for row in rows]


    def list_users(self) -> List[User]:
        """列出所有用户。

        Returns:
            全部用户列表。
        """
        with self.dbm.get_conn() as conn:
            rows = conn.execute(
                "SELECT sender_id, umo_of_bot, is_admin, nickname FROM Users ORDER BY sender_id"
            ).fetchall()
        return [User.from_db_row(row) for row in rows]

    def update_nickname(self, sender_id: str, nickname: str) -> bool:
        """更新用户的昵称。

        Args:
            sender_id: 用户唯一标识。
            nickname: 新昵称。

        Returns:
            是否更新了某行。
        """
        nick = (nickname or sender_id).strip()
        with self.dbm.get_conn() as conn:
            cur = conn.execute(
                "UPDATE Users SET nickname = ? WHERE sender_id = ?",
                (nick, sender_id),
            )
            return cur.rowcount > 0
