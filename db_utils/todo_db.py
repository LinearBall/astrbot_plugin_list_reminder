import sqlite3 as s3
from typing import List

from astrbot.api import logger

from .db_types import Todo
from .dbm import DBManager


class TodoDB:
    """存储所有待办事项的数据库。
    * 重要提示: creator由event.get_sender_id()获取
    * 重要提示: umo 唯一标识一个聊天窗口，可能是私聊或群聊
    """

    def __init__(self, dbm: DBManager) -> None:
        self.dbm = dbm

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
        with self.dbm.get_conn() as conn:
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
        with self.dbm.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "select * from Todos where todo_id = ?",
                (todo_id,),
            )
        row: s3.Row | None = cursor.fetchone()
        if row is None:
            logger.error("待办 {} 不存在".format(todo_id))
            return None
        todo = Todo.from_db_row(row)
        todo.tags = self.get_tags_by_todo(todo_id)
        return todo

    def get_tags_by_todo(self, todo_id: int) -> List[str]:
        """按待办 ID 查询其全部标签。

        Args:
            todo_id: 待办 ID。

        Returns:
            标签名列表。
        """
        with self.dbm.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT t.name FROM Tags t
                JOIN TodoTags tt ON tt.tag_id = t.tag_id
                WHERE tt.todo_id = ?""",
                (todo_id,),
            )
        return [row[0] for row in cursor.fetchall()]

    def get_todo_by_umo(self, umo: str) -> List[Todo]:
        """
        获取指定聊天窗口内布置的所有待办
        """
        with self.dbm.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "select * from Todos where umo = ?",
                (umo,),
            )
        rows: List[s3.Row] = cursor.fetchall()
        for row in rows:
            logger.info(row)
        return [Todo.from_db_row(row) for row in rows]

    def get_all_todos(self) -> List[Todo]:
        """获取所有用户创建的所有待办。"""
        with self.dbm.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("select * from Todos")
        rows: List[s3.Row] = cursor.fetchall()
        todos = [Todo.from_db_row(row) for row in rows]
        for todo in todos:
            todo.tags = self.get_tags_by_todo(todo.todo_id)
        return todos

    def get_todo_by_creator(self, creator: str) -> List[Todo]:
        """
        获取指定用户创建的所有待办
        """
        with self.dbm.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "select * from Todos where creator = ?",
                (creator,),
            )
        rows: List[s3.Row] = cursor.fetchall()
        todos = [Todo.from_db_row(row) for row in rows]
        for todo in todos:
            todo.tags = self.get_tags_by_todo(todo.todo_id)
        return todos

    def get_pending_todo_ids_with_due_time(self):
        """
        获取所有未完成的待办ID和到期时间
        """
        with self.dbm.get_conn() as conn:
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
        with self.dbm.get_conn() as conn:
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
        with self.dbm.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "update Todos set content = ?, due_time = ?, completed = ? where todo_id = ?",
                (content, due_time, int(completed), todo_id),
            )
            return cursor.rowcount > 0

    def update_todo_owner(self, todo_id: int, creator: str, umo: str) -> bool:
        """Update a todo owner and its reminder session.

        Args:
            todo_id: Todo ID.
            creator: New owner sender ID.
            umo: New owner reminder session.

        Returns:
            Whether a row was updated.
        """
        with self.dbm.get_conn() as conn:
            cur = conn.execute(
                "update Todos set creator = ?, umo = ? where todo_id = ?",
                (creator, umo, todo_id),
            )
            return cur.rowcount > 0

    def delete_todo(self, todo_id: int):
        """
        删除指定待办
        """
        with self.dbm.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "delete from Todos where todo_id = ?",
                (todo_id,),
            )

    def delete_todos_by_umo(self, umo: str):
        with self.dbm.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "delete from Todos where umo = ?",
                (umo,),
            )

    def delete_todos_by_sender_id(self, sender_id: str):
        """
        删除指定用户创建的所有待办
        """
        with self.dbm.get_conn() as conn:
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
        with self.dbm.get_conn() as conn:
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

    def delete_todos_by_todo_tag(self, tag: str) -> int:
        """根据待办标签批量删除待办。

        Args:
            tag: 标签名称。

        Returns:
            删除的待办数量。
        """
        with self.dbm.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT tt.todo_id 
                FROM TodoTags as tt
                JOIN Tags as t 
                ON t.tag_id = tt.tag_id
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
