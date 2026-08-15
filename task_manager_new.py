import asyncio
from datetime import datetime
from typing import Dict
from astrbot.api import logger
from astrbot.api.star import Context
from astrbot.core.message.message_event_result import MessageChain

from .db import TaskDB


class TaskManagerNew:
    """任务管理器 - 极简实现"""

    def __init__(self, context: Context):
        self.context = context
        self.db = TaskDB()
        self.active_timers: Dict[int, asyncio.Task] = {}  # 只存活跃定时器

    def create_task(
        self, creator: str, umo: str, group_id: str | None, content: str, due_time: int
    ) -> int:
        """
        创建一个新任务，并开始倒计时
        """
        new_task_id = self.db.add_task(creator, umo, group_id, content, due_time)
        self.count_down_to_remind(new_task_id, due_time)
        return new_task_id

    def count_down_to_remind(self, task_id: int, due_time: int):
        """
        检查倒计时时长，若为正则启动新协程进行倒计时
        """
        cur_time = datetime.now().timestamp()
        delay = due_time - cur_time
        if delay <= 0:
            logger.error("任务 {} 已过期！".format(task_id))
            return
        asyncio.create_task(self.__send_reminder_after(task_id, delay))

    async def __send_reminder_after(self, task_id: int, delay: float):
        """
        倒计时协程。完成后，将任务标记为已完成
        """
        await asyncio.sleep(delay)
        task = self.db.get_task_by_id(task_id)
        assert task is not None
        remind_msg = MessageChain().message(task.content)
        await self.context.send_message(task.umo, remind_msg)
        self.db.mark_task_as_completed(task_id)
