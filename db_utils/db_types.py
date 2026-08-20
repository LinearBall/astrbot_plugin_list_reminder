import sqlite3 as s3
from datetime import datetime
from typing import NotRequired, TypedDict

from pydantic import BaseModel


class Todo(BaseModel):
    todo_id: int
    creator: str
    umo: str
    content: str
    due_time: int
    completed: bool
    tags: list[str] = []

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
        tag_hint = (" #" + " #".join(self.tags)) if self.tags else ""
        return f"{frdly_status} [{frdly_due_time}] {self.content}{tag_hint}"


class EditTodoPayload(TypedDict):
    todo_id: int
    content: str
    due_time: int
    completed: bool
    owners: NotRequired[list[str]]
    tags: NotRequired[list[str]]


class User(BaseModel):
    sender_id: str
    umo: str
    is_admin: bool
    nickname: str = ""

    @staticmethod
    def from_db_row(row: s3.Row) -> "User":
        return User(
            sender_id=row[0],
            umo=row[1],
            is_admin=bool(row[2]),
            nickname=(row[3] if len(row) > 3 else ""),
        )
