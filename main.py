import asyncio
import json
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from dateutil import parser as dateutil_parser

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.astrbot_path import (
    get_astrbot_plugin_data_path,  # 新版插件目录
)

from . import webui


def _run_webui_worker(config, task_manager):
    """WebUI工作线程入口"""
    webui.run_server(config, task_manager)


# 配置
PLUGIN_DIR = Path(__file__).parent.absolute()
PLUGIN_NAME = "list_reminder"
PLUGIN_DATA_ROOT = (Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME).resolve()
USERS_DIR = PLUGIN_DATA_ROOT / "users"
GROUPS_DIR = PLUGIN_DATA_ROOT / "groups"

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
        self.llm_provider_id = self.config.get("llm_provider_id")
        self.schedule_detection_provider_id = self.config.get("schedule_detection_llm")

        # WebUI
        self.webui_thread = None
        self.server_key = None
        self.webui_port = self.config.get("webui_port", 5001)

        # 设置task_manager引用到webui
        webui.set_task_manager(self.task_manager)


    async def initialize(self):
        """插件初始化"""
        logger.info("ListReminderPlugin 正在加载...")
        await self.task_manager.load_pending_tasks()
        logger.info("ListReminderPlugin 加载完成")

    @filter.command_group("列表提醒")
    def reminder_commands(self):
        """列表提醒命令组
        列表
        清空
        后台
        """
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
            yield event.plain_result(
                f"⚠️ 后台管理界面已在运行中\n访问地址: http://localhost:{self.webui_port}\n登录密钥: {self.server_key}"
            )
            return

        # 启动webui
        self.server_key = self.config.get("server_key")
        if not self.server_key:
            import secrets

            self.server_key = secrets.token_urlsafe(16)

        # 在新线程中运行webui
        webui_config = dict(self.config)
        webui_config["server_key"] = self.server_key
        self.webui_thread = threading.Thread(
            target=_run_webui_worker,
            args=(webui_config, self.task_manager),
            daemon=True,
        )
        self.webui_thread.start()

        yield event.plain_result(
            f"✅ 后台管理界面已启动\n访问地址: http://localhost:{self.webui_port}\n登录密钥: {self.server_key}"
        )

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听消息，智能识别任务需求"""
        msg = event.message_str

        # 使用LLM判断是否为提醒意图
        if not await self._is_reminder_intent(msg, event):
            return

        # 确定目标ID（用户或群组）
        group_id = event.get_group_id()
        target_id = group_id if group_id else event.unified_msg_origin
        is_group = bool(group_id)

        # 使用LLM提取任务信息
        task_info = await self._extract_task(msg, event)
        if task_info is None:
            return
        if not task_info.get("time"):
            yield event.plain_result("❌ 无法识别时间，请明确提醒时间")
            return

        # 创建任务
        task_id = await self.task_manager.create_task(
            target_id=target_id,
            is_group=is_group,
            content=task_info["content"],
            task_time=task_info["time"],
            creator=event.session_id,
            umo=event.unified_msg_origin,
        )

        if task_id:
            yield event.plain_result(f"✅ 任务已创建：{task_info['content']}")
        else:
            yield event.plain_result("❌ 任务创建失败")

    async def _is_reminder_intent(self, msg: str, event: AstrMessageEvent) -> bool:
        """Use LLM to determine if the message is a reminder/task scheduling intent.

        Returns:
            True if the message is setting a reminder/task, False otherwise.
        """
        try:
            provider_id = self.schedule_detection_provider_id
            if not provider_id:
                provider_id = (
                    self.schedule_detection_provider_id
                    or await self.context.get_current_chat_provider_id(
                        umo=event.unified_msg_origin
                    )
                )

            system_prompt = (
                "判断用户消息是否是在设定提醒、任务或日程安排。"
                "返回 true 或 false\n\n"
                "示例：\n"
                "消息：提醒我明天下午3点开会\n"
                "true\n\n"
                "消息：后天上午10点记得交报告\n"
                "true\n\n"
                "消息：安排下周一早上9点半的团队会议\n"
                "true\n\n"
                "消息：别忘了吃饭\n"
                "false\n\n"
                "消息：今天天气怎么样\n"
                "false\n\n"
                "消息：帮我查一下快递\n"
                "false\n\n"
                "仅返回 true 或 false。"
            )

            resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                system_prompt=system_prompt,
                prompt=msg,
            )
            if not resp or not resp.completion_text:
                return False

            text = resp.completion_text.strip()
            # 如果回答中含有true就返回true，否则返回false
            if "true" in text:
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"判断提醒意图失败: {e}")
            return False

    async def _extract_task(self, msg: str, event: AstrMessageEvent) -> dict | None:
        """Use LLM to extract task content and time, with dateutil fallback.

        Returns:
            {"content": str, "time": str} on success,
            {"content": str, "time": ""} when time cannot be parsed,
            None on error.
        """
        try:
            provider_id = (
                self.schedule_detection_provider_id
                or await self.context.get_current_chat_provider_id(
                    umo=event.unified_msg_origin
                )
            )
            if not provider_id:
                return None

            now = datetime.now()
            weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            weekday_name = weekday_names[now.weekday()]

            # 为 few-shot 示例计算示例日期
            tomorrow = now + timedelta(days=1)
            day_after = now + timedelta(days=2)
            next_monday = now + timedelta(days=(7 - now.weekday()))

            system_prompt = (
                f"你是一个日程解析助手。当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')}"
                f"（{weekday_name}，Asia/Shanghai）。\n\n"
                "从用户消息中提取提醒任务信息，返回 JSON，格式如下：\n"
                '{"content": "任务内容简述", "date_str": "2026-07-11T15:00:00"}\n\n'
                "规则：\n"
                "- content：任务内容，简洁明了。\n"
                "- date_str：提醒时间，ISO 格式（基于上方当前时间换算）。如果用户没有指定时间，设为空字符串。\n"
                "- 如果用户说「明天」、「后天」、「下周一」、「X小时后」等相对时间，基于当前时间计算绝对日期。\n\n"
                "示例：\n"
                f"消息：提醒我明天下午3点开会\n"
                f'{{"content": "开会", "date_str": "{tomorrow.strftime("%Y-%m-%dT15:00:00")}"}}\n\n'
                f"消息：后天上午10点记得交报告\n"
                f'{{"content": "交报告", "date_str": "{day_after.strftime("%Y-%m-%dT10:00:00")}"}}\n\n'
                f"消息：安排下周一早上9点半的团队会议\n"
                f'{{"content": "团队会议", "date_str": "{next_monday.strftime("%Y-%m-%dT09:30:00")}"}}\n\n'
                "仅返回 JSON，不要其他内容。"
            )

            resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                system_prompt=system_prompt,
                prompt=msg,
            )
            if not resp or not resp.completion_text:
                return None

            # 容错解析：剥 markdown 围栏，提取 JSON 对象
            text = resp.completion_text.strip()
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.M)
            text = re.sub(r"\s*```$", "", text, flags=re.M)
            # 找第一个 { 到最后一个 }
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start == -1 or brace_end == -1:
                return None
            text = text[brace_start : brace_end + 1]

            result = json.loads(text)

            content = result.get("content", "").strip()
            date_str = result.get("date_str", "").strip()

            if not content or not date_str:
                return {"content": content, "time": ""}

            # 验证并标准化时间
            try:
                parsed = datetime.fromisoformat(date_str)
                if parsed.year < 2024 or parsed.year > 2100:
                    return {"content": content, "time": ""}
                task_time = parsed.isoformat()
            except (ValueError, TypeError):
                # dateutil 兜底解析
                try:
                    parsed = dateutil_parser.parse(date_str, fuzzy=True)
                    if parsed.year < 2024 or parsed.year > 2100:
                        parsed = parsed.replace(year=now.year)
                    task_time = parsed.isoformat()
                except (ValueError, TypeError):
                    return {"content": content, "time": ""}

            return {"content": content, "time": task_time}

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
