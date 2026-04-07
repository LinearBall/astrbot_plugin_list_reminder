import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from threading import Thread

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.message_event_result import MessageChain

from .webui import start_server

# 配置
PLUGIN_DIR = Path(__file__).parent.absolute()
DATA_DIR = PLUGIN_DIR / "data"
USERS_DIR = DATA_DIR / "users"
GROUPS_DIR = DATA_DIR / "groups"

# 确保目录存在
USERS_DIR.mkdir(parents=True, exist_ok=True)
GROUPS_DIR.mkdir(parents=True, exist_ok=True)


@register("list_reminder", "LinearBall", "智能列表式任务管理插件", "1.0.0")
class ListReminderPlugin(Star):
    """智能任务管理插件 - 支持用户和群组任务"""

    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config or {}
        self.task_manager = TaskManager(USERS_DIR, GROUPS_DIR, self.context)

        self.max_tasks_per_user = self.config.get("max_tasks_per_user", 50)
        self.schedule_detection_provider_id = self.config.get("schedule_detection_llm")

        # WebUI
        self.webui_thread = None
        self.server_key = None
        self.webui_port = self.config.get("webui_port", 5001)

        # 触发关键词
        self.trigger_keywords = ["提醒我", "设置提醒", "定时提醒", "记得", "别忘了", "安排"]

    async def initialize(self):
        """插件初始化"""
        logger.info("ListReminderPlugin 正在加载...")
        await self.task_manager.load_pending_tasks()
        logger.info("ListReminderPlugin 加载完成")

    @filter.command_group("提醒")
    def reminder_commands(self):
        """提醒命令组"""
        pass

    @reminder_commands.command("列表")
    async def list_tasks(self, event: AstrMessageEvent):
        """列出任务"""
        user_id = event.unified_msg_origin
        tasks = await self.task_manager.get_tasks(user_id)

        if not tasks:
            yield event.plain_result("📝 您当前没有待办任务")
            return

        msg = "📝 您的任务列表：\n"
        for task in tasks:
            status = "✅" if task.get("completed") else "⏰"
            msg += f"{status} [{task['time']}] {task['content']}\n"

        yield event.plain_result(msg)

    @reminder_commands.command("清空")
    async def clear_tasks(self, event: AstrMessageEvent):
        """清空所有任务"""
        user_id = event.unified_msg_origin
        await self.task_manager.clear_tasks(user_id)
        yield event.plain_result("🗑️ 任务列表已清空")

    @reminder_commands.command("后台")
    async def open_webui(self, event: AstrMessageEvent):
        """开启后台管理界面"""
        if self.webui_thread and self.webui_thread.is_alive():
            yield event.plain_result(f"⚠️ 后台管理界面已在运行中\n访问地址: http://localhost:{self.webui_port}\n登录密钥: {self.server_key}")
            return

        # 启动webui
        self.server_key = self.config.get("server_key")
        if not self.server_key:
            import secrets
            self.server_key = secrets.token_urlsafe(16)

        # 在新线程中运行webui
        def run_webui():
            asyncio.run(start_server(self.config, self.task_manager))

        self.webui_thread = Thread(target=run_webui, daemon=True)
        self.webui_thread.start()

        yield event.plain_result(f"✅ 后台管理界面已启动\n访问地址: http://localhost:{self.webui_port}\n登录密钥: {self.server_key}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听消息，智能识别任务需求"""
        msg = event.message_str

        # 简单关键词过滤
        if not any(k in msg for k in self.trigger_keywords):
            return

        # 确定目标ID（用户或群组）
        group_id = event.get_group_id()
        target_id = group_id if group_id else event.unified_msg_origin
        is_group = bool(group_id)

        # 使用LLM提取任务信息
        task_info = await self._extract_task(msg, event)
        if not task_info or not task_info.get("time"):
            yield event.plain_result("❌ 无法识别时间，请明确提醒时间")
            return

        # 创建任务
        task_id = await self.task_manager.create_task(
            target_id=target_id,
            is_group=is_group,
            content=task_info["content"],
            task_time=task_info["time"],
            creator=event.session_id,
            umo=event.unified_msg_origin
        )

        if task_id:
            yield event.plain_result(f"✅ 任务已创建：{task_info['content']}")
        else:
            yield event.plain_result("❌ 任务创建失败")

    async def _extract_task(self, msg: str, event: AstrMessageEvent) -> dict | None:
        """使用LLM提取任务信息（简化版）"""
        try:
            provider_id = self.schedule_detection_provider_id or await self.context.get_current_chat_provider_id(umo=event.unified_msg_origin)
            if not provider_id:
                return None

            prompt = f"""从以下消息提取任务信息，返回JSON：
- time: 提醒时间（ISO格式，如2024-01-01T15:00:00）
- content: 任务内容
消息：{msg}
只返回JSON，不要其他内容"""

            resp = await self.context.llm_generate(chat_provider_id=provider_id, prompt=prompt)
            if resp and resp.completion_text:
                return json.loads(resp.completion_text)

        except Exception as e:
            logger.error(f"提取任务失败: {e}")

        return None


class TaskManager:
    """任务管理器 - 极简实现"""

    def __init__(self, users_dir: Path, groups_dir: Path, context: Context):
        self.users_dir = users_dir
        self.groups_dir = groups_dir
        self.context = context
        self.active_timers: dict[str, asyncio.Task] = {}  # 只存活跃定时器

    async def load_pending_tasks(self):
        """加载待执行任务（只加载未过期的）"""
        now = datetime.now()
        loaded = 0

        # 扫描用户任务
        for user_file in self.users_dir.glob("user_*.json"):
            try:
                with open(user_file, "r", encoding="utf-8") as f:
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
                with open(group_file, "r", encoding="utf-8") as f:
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
        user_file = self.users_dir / f"user_{target_id}.json"
        if user_file.exists():
            with open(user_file, "r", encoding="utf-8") as f:
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

    async def create_task(self, target_id: str, is_group: bool, content: str,
                        task_time: str, creator: str, umo: str) -> str | None:
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
            "is_group": is_group
        }

        # 保存到文件
        if is_group:
            file = self.groups_dir / f"group_{target_id}.json"
        else:
            file = self.users_dir / f"user_{target_id}.json"

        data = {"tasks": []}
        if file.exists():
            with open(file, "r", encoding="utf-8") as f:
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
            file = self.groups_dir / f"group_{task['target_id']}.json"
        else:
            file = self.users_dir / f"user_{task['target_id']}.json"

        if file.exists():
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for t in data.get("tasks", []):
                if t["id"] == task["id"]:
                    t["completed"] = True
                    break

            with open(file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

    async def clear_tasks(self, target_id: str):
        """清空任务"""
        user_file = self.users_dir / f"user_{target_id}.json"
        if user_file.exists():
            with open(user_file, "w", encoding="utf-8") as f:
                json.dump({"tasks": []}, f, ensure_ascii=False)

        # 取消相关定时器
        to_cancel = [tid for tid in self.active_timers if tid.startswith(target_id)]
        for tid in to_cancel:
            self.active_timers[tid].cancel()
            del self.active_timers[tid]
