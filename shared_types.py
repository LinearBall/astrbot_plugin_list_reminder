from dataclasses import dataclass
from typing import TypedDict, Union
from datetime import datetime


class ReminderConfig(TypedDict):
    max_tasks_per_user: int
    llm_provider_id: str
    schedule_detection_llm: str
    webui_port: int


class RespTemplate(dict):
    def __init__(self, code: int, **kwargs):
        super().__init__()
        self.code = code
        self.payload = kwargs

    def to_dict(self):
        return {"code": self.code, "payload": self.payload}


@dataclass
class Umo:
    val: str


@dataclass
class Task:
    task_id: int
    creator: str
    umo: str
    content: str
    due_time: int
    completed: bool
