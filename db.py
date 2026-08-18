import sqlite3 as s3
from datetime import datetime
from pathlib import Path
from typing import List, TypedDict

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import (
    get_astrbot_plugin_data_path,  # 新版插件目录
)
from pydantic import BaseModel


# 配置
PLUGIN_DIR = Path(__file__).parent.absolute()
PLUGIN_NAME = "list_reminder"
PLUGIN_DATA_ROOT = (Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME).resolve()
# 确保目录存在
PLUGIN_DATA_ROOT.mkdir(parents=True, exist_ok=True)

class Todo(BaseModel):
    todo_id: int
    creator: str
    umo: str
    content: str
    due_time: int
    completed: bool

    @staticmethod
    def from_db_row(row: s3.Row) -> "Todo":
        return Todo(
            todo_id=row[0],
            creator=row[1],
            umo=row[2],
            content=row[3],
            due_time=row[4],
            completed=row[5],
        )

    def to_friendly(self) -> str:
        frdly_status = "✅" if self.completed else "⏰"
        frdly_due_time = datetime.fromtimestamp(self.due_time).isoformat()
        return "{} [{}] {}".format(frdly_status, frdly_due_time, self.content)


class EditTodoPayload(TypedDict):
    todo_id: int
    content: str
    due_time: int
    completed: bool


class User(BaseModel):
    sender_id: str
    umo: str
    is_admin: bool

    @staticmethod
    def from_db_row(row: s3.Row) -> "User":
        return User(
            sender_id=row[0],
            umo=row[1],
            is_admin=bool(row[2]),
        )


class TodoDB:
    """
    存储所有待办事项的数据库。
    * 重要提示: creator由event.get_sender_id()获取
    * 重要提示: umo 唯一标识一个聊天窗口，可能是私聊或群聊

    同时负责初始化整个 todos.db 的建表；UserDB 与 TagDB 复用其连接。
    """

    def __init__(self) -> None:
        self.db_path = PLUGIN_DATA_ROOT
        self.conn = self.ensure_db()

    def __del__(self):
        self.conn.close()

    def ensure_db(self) -> s3.Connection:
        conn = s3.connect(self.db_path / "todos.db")
        # 构造待办表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS Todos (
                todo_id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator TEXT NOT NULL,
                umo TEXT NOT NULL,
                content TEXT NOT NULL,
                due_time INTEGER NOT NULL,
                completed INTEGER DEFAULT 0
            )
        """)
        # 用户表：sender_id + 私聊窗口 umo + 管理员标记
        conn.execute("""
            CREATE TABLE IF NOT EXISTS Users (
                sender_id TEXT PRIMARY KEY,
                umo TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0
            )
        """)
        # 标签表：标签名唯一，不区分大小写
        conn.execute("""
            CREATE TABLE IF NOT EXISTS Tags (
                tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE
            )
        """)
        # 用户-标签关联表：一个用户可有多个标签，一个标签可属于多个用户
        conn.execute("""
            CREATE TABLE IF NOT EXISTS UserTags (
                sender_id TEXT NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (sender_id, tag_id),
                FOREIGN KEY (sender_id) REFERENCES Users(sender_id),
                FOREIGN KEY (tag_id) REFERENCES Tags(tag_id)
            )
        """)
        # 待办-标签关联表：一个待办可有多个标签，一个标签可属于多个待办
        conn.execute("""
            CREATE TABLE IF NOT EXISTS TodoTags (
                todo_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (todo_id, tag_id),
                FOREIGN KEY (todo_id) REFERENCES Todos(todo_id),
                FOREIGN KEY (tag_id) REFERENCES Tags(tag_id)
            )
        """)
        conn.commit()
        return conn

    def add_todo(
        self,
        creator: str,
        umo: str,
        content: str,
        due_time: float,
        completed: bool = False,
    ) -> int:
        """
        将待办添加到数据库中
        :param umo: 添加待办的聊天窗口ID
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                    insert into Todos (creator, umo, content, due_time, completed) VALUES (?, ?, ?, ?, ?)
                """,
                (creator, umo, content, due_time, int(completed)),
            )
            new_todo_id = cursor.lastrowid
        assert new_todo_id is not None
        return new_todo_id

    def get_todo_by_id(self, todo_id: int) -> Todo | None:
        """
        获取指定ID的待办
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "select * from Todos where todo_id = ?",
                (todo_id,),
            )
        row: s3.Row | None = cursor.fetchone()
        if row is None:
            logger.error("待办 {} 不存在".format(todo_id))
            return None
        return Todo.from_db_row(row)

    def get_todo_by_umo(self, umo: str) -> List[Todo]:
        """
        获取指定聊天窗口内布置的所有待办
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "select * from Todos where umo = ?",
                (umo,),
            )
        rows: List[s3.Row] = cursor.fetchall()
        for row in rows:
            logger.info(row)
        return [Todo.from_db_row(row) for row in rows]

    def get_todo_by_creator(self, creator: str) -> List[Todo]:
        """
        获取指定用户创建的所有待办
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "select * from Todos where creator = ?",
                (creator,),
            )
        rows: List[s3.Row] = cursor.fetchall()
        return [Todo.from_db_row(row) for row in rows]

    def get_pending_todo_ids_with_due_time(self):
        """
        获取所有未完成的待办ID和到期时间
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "select todo_id, due_time from Todos where completed = 0",
            )
        rows: List[s3.Row] = cursor.fetchall()
        return [(row[0], row[1]) for row in rows]

    def mark_todo_as_completed(self, todo_id: int):
        """
        标记待办为已完成
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "update Todos set completed = 1 where todo_id = ?",
                (todo_id,),
            )

    def update_todo(
        self, todo_id: int, content: str, due_time: int, completed: bool
    ) -> bool:
        """
        更新待办的内容和到期时间
        :return: 是否有更新某一行
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "update Todos set content = ?, due_time = ?, completed = ? where todo_id = ?",
                (content, due_time, int(completed), todo_id),
            )
            return cursor.rowcount > 0

    def delete_todo(self, todo_id: int):
        """
        删除指定待办
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "delete from Todos where todo_id = ?",
                (todo_id,),
            )

    def clear_todos_by_umo(self, umo: str):
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "delete from Todos where umo = ?",
                (umo,),
            )

    def clear_todos_by_sender_id(self, sender_id: str):
        """
        删除指定用户创建的所有待办
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "delete from Todos where creator = ?",
                (sender_id,),
            )

    def get_todos_by_tag(self, tag: str) -> List[Todo]:
        """根据标签批量查询待办。

        Args:
            tag: 标签名称。

        Returns:
            带有该标签的待办列表。
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT t.todo_id, t.creator, t.umo, t.content, t.due_time, t.completed
                FROM Todos t
                JOIN TodoTags tt ON tt.todo_id = t.todo_id
                JOIN Tags g ON g.tag_id = tt.tag_id
                WHERE g.name = ?
                """,
                (tag,),
            )
            rows = cursor.fetchall()
        return [Todo.from_db_row(row) for row in rows]

    def create_todos_for_tag_users(
        self,
        tag: str,
        content: str,
        due_time: float,
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
        created = []
        for user in user_db.get_users_by_tag(tag):
            todo_id = self.add_todo(user.sender_id, user.umo, content, due_time)
            tag_db.attach_tag_to_todo(todo_id, tag)
            todo = self.get_todo_by_id(todo_id)
            assert todo is not None
            created.append(todo)
        return created

    def delete_todos_by_todo_tag(self, tag: str) -> int:
        """根据待办标签批量删除待办。

        Args:
            tag: 标签名称。

        Returns:
            删除的待办数量。
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT tt.todo_id FROM TodoTags tt
                JOIN Tags t ON t.tag_id = tt.tag_id
                WHERE t.name = ?
                """,
                (tag,),
            )
            todo_ids = [row[0] for row in cursor.fetchall()]
            if not todo_ids:
                return 0
            placeholders = ",".join("?" * len(todo_ids))
            cursor.execute(
                f"DELETE FROM TodoTags WHERE todo_id IN ({placeholders})", todo_ids
            )
            cursor.execute(
                f"DELETE FROM Todos WHERE todo_id IN ({placeholders})", todo_ids
            )
        return len(todo_ids)


class UserDB:
    """用户数据库：管理与查询用户及其标签。复用 TodoDB 的连接。"""

    def __init__(self, db: "TodoDB") -> None:
        self.conn = db.conn

    def add_or_update_user(self, sender_id: str, umo: str, is_admin: bool = False) -> None:
        """新增或更新用户信息。

        Args:
            sender_id: 用户唯一标识（event.get_sender_id()）。
            umo: 用户私聊窗口对应会话的 umo。
            is_admin: 是否有管理员权限。
        """
        with self.conn as conn:
            conn.execute(
                """
                INSERT INTO Users (sender_id, umo, is_admin) VALUES (?, ?, ?)
                ON CONFLICT(sender_id) DO UPDATE SET
                    umo = excluded.umo,
                    is_admin = excluded.is_admin
                """,
                (sender_id, umo, int(is_admin)),
            )

    def get_user(self, sender_id: str) -> User | None:
        """按 sender_id 查询用户。

        Args:
            sender_id: 用户唯一标识。

        Returns:
            用户信息；不存在时返回 None。
        """
        with self.conn as conn:
            row = conn.execute(
                "SELECT sender_id, umo, is_admin FROM Users WHERE sender_id = ?",
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
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT u.sender_id, u.umo, u.is_admin
                FROM Users u
                JOIN UserTags ut ON ut.sender_id = u.sender_id
                JOIN Tags t ON t.tag_id = ut.tag_id
                WHERE t.name = ?
                """,
                (tag,),
            )
            rows = cursor.fetchall()
        return [User.from_db_row(row) for row in rows]


class TagDB:
    """标签数据库：管理标签及标签与用户/待办的关联。复用 TodoDB 的连接。"""

    def __init__(self, db: "TodoDB") -> None:
        self.conn = db.conn

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
        with self.conn as conn:
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
        with self.conn as conn:
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
        with self.conn as conn:
            conn.execute(
                "INSERT OR IGNORE INTO TodoTags (todo_id, tag_id) VALUES (?, ?)",
                (todo_id, tag_id),
            )
