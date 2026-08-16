import sqlite3 as s3
from datetime import datetime
from pathlib import Path
from typing import List, TypedDict

from astrbot.api import logger
from pydantic import BaseModel


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


class TodoDB:
    """
    存储所有待办事项的数据库。
    * 重要提示: creator由event.get_sender_id()获取
    * 重要提示: umo 唯一标识一个聊天窗口，可能是私聊或群聊
    """

    def __init__(self) -> None:
        self.db_path = Path(__file__).parent / "todos.db"
        self.conn = self.ensure_db()

    def __del__(self):
        self.conn.close()

    def ensure_db(self) -> s3.Connection:
        conn = s3.connect(self.db_path)
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
        # 迁移：删除旧版遗留的 group_id 列
        columns = {row[1] for row in conn.execute("PRAGMA table_info(Todos)")}
        if "group_id" in columns:
            conn.execute("ALTER TABLE Todos DROP COLUMN group_id")
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