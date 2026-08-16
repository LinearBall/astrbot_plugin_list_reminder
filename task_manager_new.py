import asyncio
from datetime import datetime
from typing import Dict, List

from astrbot.api import logger
from astrbot.api.star import Context
from astrbot.core.message.message_event_result import MessageChain

from .db import Task, TaskDB


class TaskManagerNew:
    """任务管理器 - 极简实现"""

    def __init__(self, context: Context):
        self.context = context
        self.db = TaskDB()
        self.active_timers: Dict[int, asyncio.Task] = {}  # 只存活跃定时器

    def create_task(
        self, creator: str, umo: str, content: str, due_time: float
    ) -> int:
        """
        创建一个新任务，并开始倒计时。若创建失败，则返回-1
        """
        new_task_id = self.db.add_task(creator, umo, content, due_time)
        if (
            count_down_task := self.count_down_to_remind(new_task_id, due_time)
        ) is not None:
            self.active_timers[new_task_id] = count_down_task
            return new_task_id
        return -1

    async def count_down_for_pending_tasks_immediately(self):
        """
        从数据库加载所有未完成任务，立即开始倒计时
        """
        pending_tasks = self.db.get_pending_task_ids_with_due_time()
        for task_id, due_time in pending_tasks:
            if (
                self.active_timers.get(task_id) is None
                and (count_down_task := self.count_down_to_remind(task_id, due_time))
                is not None
            ):
                self.active_timers[task_id] = count_down_task

    def count_down_to_remind(self, task_id: int, due_time: float) -> asyncio.Task | None:
        """
        检查倒计时时长。若为正，则启动新协程进行倒计时，并返回该协程；否则返回None
        """
        cur_time = datetime.now().timestamp()
        delay = due_time - cur_time
        if delay <= 0:
            logger.error("任务 {} 已过期！".format(task_id))
            return None
        return asyncio.create_task(self.__send_reminder_after(task_id, delay))

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
        del self.active_timers[task_id]

    def get_tasks_by_umo(self, umo: str) -> List[Task]:
        """
        获取指定聊天窗口内布置的所有任务
        """
        return self.db.get_tasks_by_umo(umo)

    def clear_tasks_by_umo(self, umo: str):
        """
        清空指定聊天窗口内布置的所有任务
        """
        tasks_to_clear = self.get_tasks_by_umo(umo)
        for task in tasks_to_clear:
            del self.active_timers[task.task_id]
        self.db.clear_tasks_by_umo(umo)

    def get_tasks_by_creator(self, creator: str) -> List[Task]:
        """
        获取指定用户创建的所有任务
        """
        return self.db.get_tasks_by_creator(creator)

    def clear_tasks_by_sender_id(self, sender_id: str):
        """
        清空指定用户创建的所有任务
        """
        tasks_to_clear = self.get_tasks_by_creator(sender_id)
        for task in tasks_to_clear:
            del self.active_timers[task.task_id]
        self.db.clear_tasks_by_sender_id(sender_id)
