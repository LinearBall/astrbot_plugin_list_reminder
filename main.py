import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import TypedDict

from dateutil import parser as dateutil_parser

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from . import webui
from .config import USERS_DIR
from .task_manager_new import TaskManagerNew

# from astrbot.core.message.message_event_result import MessageChain


class ReminderConfig(TypedDict):
    max_tasks_per_user: int
    llm_provider_id: str
    schedule_detection_llm: str
    webui_port: int
    server_key: str


@register("list_reminder", "LinearBall", "智能列表式任务管理插件", "1.1.1")
class ListReminderPlugin(Star):
    """智能任务管理插件 - 支持用户和群组任务"""

    def __init__(self, context: Context, config: ReminderConfig):
        super().__init__(context)
        self.config = config or {}
        # self.task_manager = TaskManager(USERS_DIR, GROUPS_DIR, self.context)
        self.task_manager_new = TaskManagerNew(self.context)

        self.max_tasks_per_user = self.config.get("max_tasks_per_user", 50)
        self.llm_provider_id = self.config.get("llm_provider_id")
        self.schedule_detection_provider_id = self.config.get("schedule_detection_llm")

        # WebUI
        self.webui_task: asyncio.Task | None = None
        self.webui_port = self.config.get("webui_port", 5001)

        # 设置task_manager引用到webui
        webui.set_task_manager(self.task_manager_new)

    async def initialize(self):
        """插件初始化"""
        logger.info("ListReminderPlugin 正在加载...")
        await self.task_manager_new.count_down_for_pending_tasks_immediately()
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
        sender_id = event.get_sender_id()
        tasks = self.task_manager_new.get_tasks_by_creator(sender_id)

        if not tasks:
            yield event.plain_result("📝 您当前没有待办任务")
            return

        msg = "📝 您的任务列表：\n"
        for task in tasks:
            msg += task.to_friendly() + "\n"

        yield event.plain_result(msg)

    @reminder_commands.command("清空")
    async def clear_tasks(self, event: AstrMessageEvent):
        """清空所有任务"""
        sender_id = event.get_sender_id()
        self.task_manager_new.clear_tasks_by_sender_id(sender_id)
        yield event.plain_result("🗑️ 任务列表已清空")

    @reminder_commands.command("后台")
    async def open_webui(self, event: AstrMessageEvent):
        """
        开启后台管理界面。副作用包括：
        - 启动协程，Host前端给用户访问
        - 为当前用户分配新的个人密钥，并注册到`LOGIN_KEYS`，以供登陆验证用
        """

        # 识别当前用户？
        sender_id = event.get_sender_id()
        # 服务器未运行才启动（不再需要传 server_key）
        if self.webui_task is None or self.webui_task.done():
            self.webui_task = asyncio.create_task(
                webui.start_server(self.config, self.task_manager_new)
            )
        # 为当前用户注册新的个人密钥（绑定 sender_id）
        key = webui.issue_login_key(sender_id)
        yield event.plain_result(
            f"✅ 后台已就绪\n访问地址: http://localhost:{self.webui_port}/login\n登录密钥: {key}\n（密钥仅您本人可用，只能看到自己的任务）"
        )

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听消息，智能识别任务需求"""
        msg = event.message_str
        sender_id = event.get_sender_id()
        umo = event.unified_msg_origin

        # 使用LLM判断是否为提醒意图
        if not await self._is_reminder_intent(msg, event):
            return

        # 使用LLM提取任务信息
        task_info = await self._extract_task(msg, event)
        if task_info is None:
            return
        if not task_info.get("time"):
            yield event.plain_result("❌ 无法识别时间，请明确提醒时间")
            return

        # 创建任务
        due_timestamp = datetime.fromisoformat(task_info["time"])
        task_id = self.task_manager_new.create_task(
            creator=sender_id,
            umo=umo,
            content=task_info["content"],
            due_time=due_timestamp.timestamp(),
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
