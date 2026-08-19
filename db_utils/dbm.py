import sqlite3 as s3
from pathlib import Path

from ..consts import PLUGIN_DATA_ROOT

# SQL语句
SQL_CREATE_TABLES: str = """
CREATE TABLE IF NOT EXISTS Todos (
    todo_id INTEGER PRIMARY KEY AUTOINCREMENT,
    creator TEXT NOT NULL,
    umo TEXT NOT NULL,
    content TEXT NOT NULL,
    due_time INTEGER NOT NULL,
    completed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS Users (
    sender_id TEXT PRIMARY KEY,
    umo_of_bot TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS Tags (
    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);
CREATE TABLE IF NOT EXISTS UserTags (
    sender_id TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (sender_id, tag_id),
    FOREIGN KEY (sender_id) REFERENCES Users(sender_id),
    FOREIGN KEY (tag_id) REFERENCES Tags(tag_id)
);
CREATE TABLE IF NOT EXISTS TodoTags (
    todo_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (todo_id, tag_id),
    FOREIGN KEY (todo_id) REFERENCES Todos(todo_id),
    FOREIGN KEY (tag_id) REFERENCES Tags(tag_id)
);
"""


class DBManager:
    """统一维护表结构和数据库连接"""

    def __init__(self, data_path: Path = PLUGIN_DATA_ROOT) -> None:
        self.db_path = data_path / "memo.db"
        self.__conn: s3.Connection | None = None
        self.init_db()

    def get_conn(self):
        if self.__conn is None:
            self.__conn = s3.connect(self.db_path, check_same_thread=False)
            self.__conn.row_factory = s3.Row
            self.__conn.execute("PRAGMA foreign_keys = ON;")
        return self.__conn

    def close(self):
        if (conn := self.__conn) is not None:
            conn.commit()
            conn.close()
            self.__conn = None

    def init_db(self):
        with self.get_conn() as conn:
            conn.executescript(SQL_CREATE_TABLES)
