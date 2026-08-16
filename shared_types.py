from dataclasses import dataclass
from typing import TypedDict


class ReminderConfig(TypedDict):
    max_tasks_per_user: int
    llm_provider_id: str
    schedule_detection_llm: str
    webui_port: int


@dataclass
class Umo:
    val: str


class LoginPayload(TypedDict):
    key: str