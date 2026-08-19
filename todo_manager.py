import asyncio
from datetime import datetime
from typing import Dict, List
from venv import logger

from astrbot.api.star import Context
from astrbot.core.message.message_event_result import MessageChain

from .db_utils import DBManager, TagDB, Todo, TodoDB, UserDB


def get_delay(due_time: float):
    """按照到期时间计算，多少时间以后发送提醒。

    如果返回负值，则说明到期时间设置得太早。换句话说，任务已过期。
    """
    return due_time - datetime.now().timestamp()


class TodoManager:
    """任务管理器 - 极简实现"""

    def __init__(self, context: Context):
        self.context = context
        self.dbm = DBManager()
        self.db = TodoDB(self.dbm)
        self.user_db = UserDB(self.dbm)
        self.tag_db = TagDB(self.dbm)
        self.active_timers: Dict[int, asyncio.Task] = {}  # 只存活跃定时器

    def __del__(self):
        self.dbm.close()

    def create_todo(
        self,
        creator: str,
        umo: str,
        content: str,
        due_time: float,
        completed: bool = False,
        tags: List[str] | None = None,
    ) -> int:
        """
        创建一个新任务，并开始倒计时。若创建失败，则返回-1

        Args:
            creator: 任务创建者 sender_id。
            umo: 所在会话的 umo。
            content: 任务内容。
            due_time: 到期时间戳。
            completed: 是否已完成。
            tags: 任务标签，可为空。
        """
        if get_delay(due_time) < 0:
            return -1

        new_todo_id = self.db.add_todo(creator, umo, content, due_time, completed)
        # 去空、去重（不区分大小写）后附加标签
        seen = set()
        for item in tags or []:
            if not isinstance(item, str):
                continue
            tag = item.strip()
            key = tag.casefold()
            if not tag or key in seen:
                continue
            seen.add(key)
            self.tag_db.attach_tag_to_todo(new_todo_id, tag)
        self.active_timers[new_todo_id] = self.count_down_to_remind(
            new_todo_id, due_time
        )
        return new_todo_id

    def update_todo(
        self, todo_id: int, content: str, due_time: int, completed: bool
    ) -> int:
        """
        更新任务内容与到期时间。
        若任务存在则更新并重设定时器，返回原todo_id；否则返回 -1。
        """
        todo = self.db.get_todo_by_id(todo_id)
        if todo is None:
            return -1

        updated = self.db.update_todo(todo_id, content, due_time, completed)
        if not updated:
            return -1

        # 取消旧的定时器，根据新的到期时间重新安排
        old_timer = self.active_timers.pop(todo_id, None)
        if old_timer and not old_timer.done():
            old_timer.cancel()

        updated_todo = self.db.get_todo_by_id(todo_id)
        if (
            updated_todo is not None
            and not updated_todo.completed
            and get_delay(due_time) > 0
        ):
            self.active_timers[todo_id] = self.count_down_to_remind(todo_id, due_time)

        return todo_id

    async def count_down_for_pending_todos_immediately(self):
        """
        从数据库加载所有未完成任务，立即开始倒计时
        """
        pending_todos = self.db.get_pending_todo_ids_with_due_time()
        for todo_id, due_time in pending_todos:
            if todo_id not in self.active_timers and get_delay(due_time) > 0:
                self.active_timers[todo_id] = self.count_down_to_remind(
                    todo_id, due_time
                )
            else:
                # 设置1秒后提醒，近似于立即提醒，但不能立即提醒，会报错
                self.active_timers[todo_id] = self.count_down_to_remind(
                    todo_id, datetime.now().timestamp() + 1
                )
        logger.info("成功恢复了{}个活待办事项".format(len(pending_todos)))

    def count_down_to_remind(self, todo_id: int, due_time: float) -> asyncio.Task:
        """
        启动新协程进行倒计时，并返回该协程
        """
        return asyncio.create_task(
            self.__send_reminder_after(todo_id, get_delay(due_time))
        )

    async def __send_reminder_after(self, todo_id: int, delay: float):
        """
        倒计时协程。完成后，将任务标记为已完成
        """
        await asyncio.sleep(delay)
        todo = self.db.get_todo_by_id(todo_id)
        assert todo is not None
        remind_text = todo.content
        if todo.tags:
            remind_text += "  #" + " #".join(todo.tags)
        remind_msg = MessageChain().message(remind_text)
        await self.context.send_message(todo.umo, remind_msg)
        self.db.mark_todo_as_completed(todo_id)
        del self.active_timers[todo_id]

    def get_todos_by_umo(self, umo: str) -> List[Todo]:
        """
        获取指定聊天窗口内布置的所有任务
        """
        return self.db.get_todo_by_umo(umo)

    def clear_todos_by_umo(self, umo: str):
        """
        清空指定聊天窗口内布置的所有任务
        """
        todos_to_clear = self.get_todos_by_umo(umo)
        for each in todos_to_clear:
            del self.active_timers[each.todo_id]
        self.db.delete_todos_by_umo(umo)

    def get_all_todos(self) -> List[Todo]:
        """获取所有用户创建的所有任务。"""
        return self.db.get_all_todos()

    def get_todos_by_creator(self, creator: str) -> List[Todo]:
        """
        获取指定用户创建的所有任务
        """
        return self.db.get_todo_by_creator(creator)

    def clear_todos_by_sender_id(self, sender_id: str):
        """
        清空指定用户创建的所有任务
        """
        tasks_to_clear = self.get_todos_by_creator(sender_id)
        for task in tasks_to_clear:
            del self.active_timers[task.todo_id]
        self.db.delete_todos_by_sender_id(sender_id)
