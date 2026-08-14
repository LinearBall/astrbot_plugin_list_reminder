import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from astrbot.api import logger
from astrbot.api.star import Context
from astrbot.core.message.message_event_result import MessageChain


class TaskManager:
    """任务管理器 - 极简实现"""

    def __init__(self, users_dir: Path, groups_dir: Path, context: Context):
        self.users_dir = users_dir
        self.groups_dir = groups_dir
        self.context = context
        self.active_timers: dict[str, asyncio.Task] = {}  # 只存活跃定时器

    @staticmethod
    def _sanitize_id(raw: str) -> str:
        """Replace Windows filename illegal characters with underscores."""
        for ch in ("<", ">", ":", '"', "/", "\\", "|", "?", "*"):
            raw = raw.replace(ch, "_")
        return raw

    async def load_pending_tasks(self):
        """加载待执行任务（只加载未过期的）"""
        now = datetime.now()
        loaded = 0

        # 扫描用户任务
        for user_file in self.users_dir.glob("user_*.json"):
            try:
                with open(user_file, encoding="utf-8") as f:
                    data = json.load(f)
                    for task in data.get("tasks", []):
                        if not task.get("completed"):
                            task_time = datetime.fromisoformat(task["time"])
                            if task_time > now:
                                await self.start_timer(task)
                                loaded += 1
            except Exception:
                pass

        # 扫描群组任务
        for group_file in self.groups_dir.glob("group_*.json"):
            try:
                with open(group_file, encoding="utf-8") as f:
                    data = json.load(f)
                    for task in data.get("tasks", []):
                        if not task.get("completed"):
                            task_time = datetime.fromisoformat(task["time"])
                            if task_time > now:
                                await self.start_timer(task)
                                loaded += 1
            except Exception:
                pass

        logger.info(f"加载了 {loaded} 个待执行任务")

    async def get_tasks(self, target_id: str) -> list[dict]:
        """获取任务（按需读取文件），自动标记过期任务为已完成"""
        now = datetime.now()
        changed = False
        user_file = self.users_dir / f"user_{self._sanitize_id(target_id)}.json"
        if user_file.exists():
            with open(user_file, encoding="utf-8") as f:
                data = json.load(f)
                tasks = data.get("tasks", [])
                # 自动标记过期任务为已完成
                for task in tasks:
                    if not task.get("completed"):
                        try:
                            task_time = datetime.fromisoformat(task["time"])
                            if task_time <= now:
                                task["completed"] = True
                                changed = True
                        except Exception:
                            pass
                # 如果有变更，保存
                if changed:
                    with open(user_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False)
                return tasks
        return []

    async def create_task(
        self,
        target_id: str,
        is_group: bool,
        content: str,
        task_time: str,
        creator: str,
        umo: str,
    ) -> str | None:
        """创建任务"""
        task_id = f"{target_id}_{int(time.time())}"

        # 检查时间是否已过期
        try:
            task_time_dt = datetime.fromisoformat(task_time)
            if task_time_dt <= datetime.now():
                logger.warning(f"任务时间已过期: {task_time}")
                return None
        except Exception:
            logger.error(f"时间格式错误: {task_time}")
            return None

        task = {
            "id": task_id,
            "target_id": target_id,
            "time": task_time,
            "content": content,
            "creator": creator,
            "umo": umo,
            "created_at": datetime.now().isoformat(),
            "completed": False,
            "is_group": is_group,
        }

        # 保存到文件
        if is_group:
            file = self.groups_dir / f"group_{self._sanitize_id(target_id)}.json"
        else:
            file = self.users_dir / f"user_{self._sanitize_id(target_id)}.json"

        data = {"tasks": []}
        if file.exists():
            with open(file, encoding="utf-8") as f:
                data = json.load(f)

        data["tasks"].append(task)

        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        # 启动定时器
        await self.start_timer(task)

        return task_id

    async def start_timer(self, task: dict):
        """启动定时器"""
        try:
            task_time = datetime.fromisoformat(task["time"])
            delay = (task_time - datetime.now()).total_seconds()

            if delay > 0:
                timer = asyncio.create_task(self._execute_task(task, delay))
                self.active_timers[task["id"]] = timer
        except Exception as e:
            logger.error(f"启动定时器失败: {e}")

    async def _execute_task(self, task: dict, delay: float):
        """执行任务"""
        await asyncio.sleep(delay)

        # 发送提醒
        try:
            msg = f"⏰ 提醒：{task['content']}"
            message_chain = MessageChain().message(msg)
            await self.context.send_message(task["umo"], message_chain)
            logger.info(f"任务执行: {task['content']}")
        except Exception as e:
            logger.error(f"发送提醒失败: {e}")

        # 清理
        self.active_timers.pop(task["id"], None)

        # 标记任务完成
        await self._mark_completed(task)

    async def _mark_completed(self, task: dict):
        """标记任务完成"""
        if task["is_group"]:
            file = (
                self.groups_dir / f"group_{self._sanitize_id(task['target_id'])}.json"
            )
        else:
            file = self.users_dir / f"user_{self._sanitize_id(task['target_id'])}.json"

        if file.exists():
            with open(file, encoding="utf-8") as f:
                data = json.load(f)

            for t in data.get("tasks", []):
                if t["id"] == task["id"]:
                    t["completed"] = True
                    break

            with open(file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

    async def clear_tasks(self, target_id: str):
        """清空任务"""
        user_file = self.users_dir / f"user_{self._sanitize_id(target_id)}.json"
        if user_file.exists():
            with open(user_file, "w", encoding="utf-8") as f:
                json.dump({"tasks": []}, f, ensure_ascii=False)

        # 取消相关定时器
        to_cancel = [tid for tid in self.active_timers if tid.startswith(target_id)]
        for tid in to_cancel:
            self.active_timers[tid].cancel()
            del self.active_timers[tid]
