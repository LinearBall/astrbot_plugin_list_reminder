import sqlite3 as s3
from datetime import datetime
from pathlib import Path
from typing import List

from astrbot.api import logger
from pydantic import BaseModel, field_serializer


class Task(BaseModel):
    task_id: int
    creator: str
    umo: str
    content: str
    due_time: int
    completed: bool

    @staticmethod
    def from_db_row(row: s3.Row) -> "Task":
        return Task(
            task_id=row[0],
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


class TaskDB:
    """
    存储所有任务的数据库。
    * 重要提示: creator由event.get_sender_id()获取
    * 重要提示: umo 唯一标识一个聊天窗口，可能是私聊或群聊
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
        # 迁移：删除旧版遗留的 group_id 列
        columns = {row[1] for row in conn.execute("PRAGMA table_info(Tasks)")}
        if "group_id" in columns:
            conn.execute("ALTER TABLE Tasks DROP COLUMN group_id")
        conn.commit()
        return conn

    def add_task(
        self,
        creator: str,
        umo: str,
        content: str,
        due_time: float,
    ) -> int:
        """
        将任务添加到数据库中
        :param umo: 添加任务的聊天窗口ID
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
        """
        获取指定任务ID的任务
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
        return Task.from_db_row(row)

    def get_tasks_by_umo(self, umo: str) -> List[Task]:
        """
        获取指定聊天窗口内布置的所有任务
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
        return [Task.from_db_row(row) for row in rows]

    def get_tasks_by_creator(self, creator: str) -> List[Task]:
        """
        获取指定用户创建的所有任务
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "select * from Tasks where creator = ?",
                (creator,),
            )
        rows: List[s3.Row] = cursor.fetchall()
        return [Task.from_db_row(row) for row in rows]

    def get_pending_task_ids_with_due_time(self):
        """
        获取所有未完成的任务ID和到期时间
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "select task_id, due_time from Tasks where completed = 0",
            )
        rows: List[s3.Row] = cursor.fetchall()
        return [(row[0], row[1]) for row in rows]

    def mark_task_as_completed(self, task_id: int):
        """
        标记任务为已完成
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "update Tasks set completed = 1 where task_id = ?",
                (task_id,),
            )

    def delete_task(self, task_id: int):
        """
        删除指定任务
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "delete from Tasks where task_id = ?",
                (task_id,),
            )

    def clear_tasks_by_umo(self, umo: str):
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "delete from Tasks where umo = ?",
                (umo,),
            )

    def clear_tasks_by_sender_id(self, sender_id: str):
        """
        删除指定用户创建的所有任务
        """
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute(
                "delete from Tasks where creator = ?",
                (sender_id,),
            )
