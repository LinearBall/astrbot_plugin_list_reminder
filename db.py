import asyncio
import sqlite3 as s3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from astrbot.api import logger


@dataclass
class Task:
    task_id: int
    creator: str
    umo: str
    content: str
    due_time: int
    completed: bool


@dataclass
class User:
    sender_id: str
    umo: str
    is_admin: bool


class TaskDB:
    """任务数据库：负责任务的增删改查，以及按标签查询/创建/删除任务。

    同时负责初始化整个 tasks.db 的建表；UserDB 与 TagDB 复用其连接。
    """

    def __init__(self) -> None:
        self.db_path = Path(__file__).parent / "tasks.db"
        self.conn = self.ensure_db()

    def __del__(self):
        self.conn.close()

    def ensure_db(self) -> s3.Connection:
        conn = s3.connect(self.db_path)
        # 构造任务表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS Tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        # 任务-标签关联表：一个任务可有多个标签，一个标签可属于多个任务
        conn.execute("""
            CREATE TABLE IF NOT EXISTS TaskTags (
                task_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (task_id, tag_id),
                FOREIGN KEY (task_id) REFERENCES Tasks(task_id),
                FOREIGN KEY (tag_id) REFERENCES Tags(tag_id)
            )
        """)
        conn.commit()
        return conn

    def add_task(
        self,
        creator: str,
        umo: str,
        content: str,
        due_time: float,
    ) -> int:
        """将任务添加到数据库中。

        Args:
            creator: 创建者 sender_id。
            umo: 添加任务的聊天窗口ID。
            content: 任务内容。
            due_time: 到期时间戳。

        Returns:
            新任务 ID。
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                    insert into Tasks (creator, umo, content, due_time) VALUES (?, ?, ?, ?)
                """,
                (creator, umo, content, due_time),
            )
            new_task_id = cursor.lastrowid
        assert new_task_id is not None
        return new_task_id

    def get_task_by_id(self, task_id: int) -> Task | None:
        """获取指定任务ID的任务。

        Args:
            task_id: 任务 ID。

        Returns:
            任务信息；不存在时返回 None。
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "select * from Tasks where task_id = ?",
                (task_id,),
            )
        row: s3.Row | None = cursor.fetchone()
        if row is None:
            logger.error("任务 {} 不存在".format(task_id))
            return None
        return Task(*row)

    def mark_task_as_completed(self, task_id: int):
        """标记任务为已完成。

        Args:
            task_id: 任务 ID。
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "update Tasks set completed = 1 where task_id = ?",
                (task_id,),
            )

    def delete_task(self, task_id: int):
        """删除指定任务。

        Args:
            task_id: 任务 ID。
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "delete from Tasks where task_id = ?",
                (task_id,),
            )

    def clear_tasks_by_umo(self, umo: str):
        """清空指定聊天窗口内的所有任务。

        Args:
            umo: 聊天窗口ID。
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "delete from Tasks where umo = ?",
                (umo,),
            )

    def clear_tasks_by_sender_id(self, sender_id: str):
        """删除指定用户创建的所有任务。

        Args:
            sender_id: 用户唯一标识。
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "delete from Tasks where creator = ?",
                (sender_id,),
            )

    def get_tasks_by_umo(self, umo: str) -> List[Task]:
        """获取指定聊天窗口内布置的所有任务。

        Args:
            umo: 聊天窗口ID。

        Returns:
            任务列表。
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "select * from Tasks where umo = ?",
                (umo,),
            )
        rows: List[s3.Row] = cursor.fetchall()
        for row in rows:
            logger.info(row)
        return [Task(*row) for row in rows]

    def get_tasks_by_creator(self, creator: str) -> List[Task]:
        """获取指定用户创建的所有任务。

        Args:
            creator: 用户 sender_id。

        Returns:
            任务列表。
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "select * from Tasks where creator = ?",
                (creator,),
            )
        rows: List[s3.Row] = cursor.fetchall()
        return [Task(*row) for row in rows]

    def get_pending_task_ids_with_due_time(self):
        """获取所有未完成的任务ID和到期时间。

        Returns:
            (task_id, due_time) 元组列表。
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "select task_id, due_time from Tasks where completed = 0",
            )
        rows: List[s3.Row] = cursor.fetchall()
        return [(row[0], row[1]) for row in rows]

    def get_tasks_by_tag(self, tag: str) -> List[Task]:
        """根据标签批量查询任务。

        Args:
            tag: 标签名称。

        Returns:
            带有该标签的任务列表。
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT t.task_id, t.creator, t.umo, t.content, t.due_time, t.completed
                FROM Tasks t
                JOIN TaskTags tt ON tt.task_id = t.task_id
                JOIN Tags g ON g.tag_id = tt.tag_id
                WHERE g.name = ?
                """,
                (tag,),
            )
            rows = cursor.fetchall()
        return [Task(*row) for row in rows]

    def create_tasks_for_tag_users(
        self,
        tag: str,
        content: str,
        due_time: float,
        user_db: "UserDB",
        tag_db: "TagDB",
    ) -> List[Task]:
        """给所有带有指定标签的用户批量创建任务。

        Args:
            tag: 标签名称。
            content: 任务内容。
            due_time: 到期时间戳。
            user_db: 用户数据库实例，用于按标签查找用户。
            tag_db: 标签数据库实例，用于给新任务打标签。

        Returns:
            创建出的任务列表。
        """
        created = []
        for user in user_db.get_users_by_tag(tag):
            task_id = self.add_task(user.sender_id, user.umo, content, due_time)
            tag_db.attach_tag_to_task(task_id, tag)
            task = self.get_task_by_id(task_id)
            assert task is not None
            created.append(task)
        return created

    def delete_tasks_by_task_tag(self, tag: str) -> int:
        """根据任务标签批量删除任务。

        Args:
            tag: 标签名称。

        Returns:
            删除的任务数量。
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT tt.task_id FROM TaskTags tt
                JOIN Tags t ON t.tag_id = tt.tag_id
                WHERE t.name = ?
                """,
                (tag,),
            )
            task_ids = [row[0] for row in cursor.fetchall()]
            if not task_ids:
                return 0
            placeholders = ",".join("?" * len(task_ids))
            cursor.execute(
                f"DELETE FROM TaskTags WHERE task_id IN ({placeholders})", task_ids
            )
            cursor.execute(
                f"DELETE FROM Tasks WHERE task_id IN ({placeholders})", task_ids
            )
        return len(task_ids)


class UserDB:
    """用户数据库：管理与查询用户及其标签。复用 TaskDB 的连接。"""

    def __init__(self, db: TaskDB) -> None:
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
        return User(row[0], row[1], bool(row[2]))

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
        return [User(row[0], row[1], bool(row[2])) for row in rows]


class TagDB:
    """标签数据库：管理标签及标签与用户/任务的关联。复用 TaskDB 的连接。"""

    def __init__(self, db: TaskDB) -> None:
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

    def attach_tag_to_task(self, task_id: int, tag: str) -> None:
        """给任务附加一个标签。

        Args:
            task_id: 任务 ID。
            tag: 标签名称。
        """
        tag_id = self.get_or_create_tag(tag)
        with self.conn as conn:
            conn.execute(
                "INSERT OR IGNORE INTO TaskTags (task_id, tag_id) VALUES (?, ?)",
                (task_id, tag_id),
            )
