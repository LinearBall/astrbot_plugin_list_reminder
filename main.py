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

from . import webui
from .config import USER_TAGS_FILE, USERS_DIR
from .tag_utils import (
    find_users_by_tag,
    load_user_tags,
    normalize_tags,
    save_user_tags,
)


def _run_webui_worker(config, task_manager):
    # WebUI 工作线程入口函数
    webui.run_server(config, task_manager)


@register("list_reminder", "LinearBall", "智能列表式任务管理插件", "1.3.0")
class ListReminderPlugin(Star):
    # 智能任务管理插件主类

    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config or {}
        self.task_manager = TaskManager(USERS_DIR, USER_TAGS_FILE, self.context)

        self.max_tasks_per_user = self.config.get("max_tasks_per_user", 50)
        self.llm_provider_id = self.config.get("llm_provider_id")
        self.schedule_detection_provider_id = self.config.get("schedule_detection_llm")

        # WebUI 相关状态
        self._webui_started = False
        self._webui_start_lock = threading.Lock()
        self.webui_port = int(self.config.get("webui_port", 5001))

        # 管理员 sender_id 列表（不区分大小写匹配）
        raw_admins = self.config.get("admin_sender_ids") or []
        if isinstance(raw_admins, str):
            raw_admins = [
                s.strip() for s in raw_admins.replace("，", ",").split(",") if s.strip()
            ]
        self._admin_sender_ids: set[str] = {
            str(s).strip() for s in raw_admins if str(s).strip()
        }

        # 为 webui 模块设置 task_manager 引用
        webui.set_task_manager(self.task_manager)

    async def initialize(self):
        # 插件初始化：加载待执行任务
        logger.info("ListReminderPlugin 正在加载...")
        await self.task_manager.load_pending_tasks()
        logger.info("ListReminderPlugin 加载完成")

    def _is_admin(self, sender_id: str) -> bool:
        # 判断发送者是否为管理员
        return bool(sender_id and sender_id in self._admin_sender_ids)

    def _ensure_webui_server(self) -> bool:
        # 首次调用时启动 WebUI 服务器（单例），返回是否运行中
        if self._webui_started:
            return True
        with self._webui_start_lock:
            if self._webui_started:
                return True
            try:
                webui_config = dict(self.config)
                t = threading.Thread(
                    target=_run_webui_worker,
                    args=(webui_config, self.task_manager),
                    daemon=True,
                )
                t.start()
                self._webui_started = True
                # Small delay so hypercorn has a chance to bind the port
                time.sleep(0.3)
                return True
            except Exception as e:
                logger.error(f"启动 WebUI 服务器失败: {e}")
                return False

    @filter.command_group("列表提醒")
    def reminder_commands(self):
        """列表提醒命令组:
        列表
        清空
        开启后台
        关闭后台
        管理员后台
        """
        pass

    @reminder_commands.command("列表")
    async def list_tasks(self, event: AstrMessageEvent):
        # 列出当前用户的所有任务
        user_id = event.get_sender_id()
        tasks = await self.task_manager.get_tasks(user_id)

        if not tasks:
            yield event.plain_result("📝 您当前没有待办任务")
            return

        msg = "📝 您的任务列表：\n"
        for task in tasks:
            status = "✅" if task.get("completed") else "⏰"
            tag_hint = ""
            if task.get("tags"):
                tag_hint = " #" + " #".join(task["tags"])
            msg += f"{status} [{task['time']}] {task['content']}{tag_hint}\n"

        yield event.plain_result(msg)

    @reminder_commands.command("清空")
    async def clear_tasks(self, event: AstrMessageEvent):
        # 清空当前用户的所有任务
        user_id = event.get_sender_id()
        await self.task_manager.clear_tasks(user_id)
        yield event.plain_result("🗑️ 任务列表已清空")

    @reminder_commands.command("开启后台")
    async def open_webui(self, event: AstrMessageEvent):
        """开启个人后台管理界面（仅能看到自己的任务）"""
        sender_id = event.get_sender_id()
        if not self._ensure_webui_server():
            yield event.plain_result("❌ 后台服务器启动失败")
            return

        key = webui.issue_login_key(sender_id, is_admin=False)
        public_ip = str(self.config.get("webui_public_ip") or "").strip()
        url_list = webui.get_access_urls(self.webui_port, public_ip)
        msg_lines = ["✅ 个人后台已就绪"]
        for label, base_url in url_list:
            msg_lines.append(f"{label}: {base_url}/login?key={key}")
        msg_lines.append("（点击直达登录，密钥仅您本人可用，发送“关闭后台”可立即失效）")
        yield event.plain_result("\n".join(msg_lines))

    @reminder_commands.command("关闭后台")
    async def close_webui(self, event: AstrMessageEvent):
        """关闭个人后台（立即失效个人登录密钥，不影响管理员密钥和服务器）"""
        sender_id = event.get_sender_id()
        removed = webui.revoke_login_key(sender_id, admin_only=False)
        if removed > 0:
            yield event.plain_result(f"🔒 已关闭个人后台，{removed} 个登录密钥已失效")
        else:
            yield event.plain_result("ℹ️ 当前没有有效的个人后台登录密钥")

    @reminder_commands.command("管理员后台")
    async def admin_webui(self, event: AstrMessageEvent):
        """开启管理员后台（仅管理员可用，可查看和管理所有任务）"""
        sender_id = event.get_sender_id()
        if not self._is_admin(sender_id):
            yield event.plain_result("❌ 您没有管理员权限")
            return

        if not self._ensure_webui_server():
            yield event.plain_result("❌ 后台服务器启动失败")
            return

        key = webui.issue_login_key(sender_id, is_admin=True)
        public_ip = str(self.config.get("webui_public_ip") or "").strip()
        url_list = webui.get_access_urls(self.webui_port, public_ip)
        msg_lines = ["✅ 管理员后台已就绪"]
        for label, base_url in url_list:
            msg_lines.append(f"{label}: {base_url}/login?key={key}")
        msg_lines.append(
            "（点击直达登录，密钥仅您本人可用，发送“关闭管理员后台”可立即失效）"
        )
        yield event.plain_result("\n".join(msg_lines))

    @reminder_commands.command("关闭管理员后台")
    async def close_admin_webui(self, event: AstrMessageEvent):
        """关闭管理员后台（仅管理员可用，立即失效管理员登录密钥）"""
        sender_id = event.get_sender_id()
        if not self._is_admin(sender_id):
            yield event.plain_result("❌ 您没有管理员权限")
            return

        removed = webui.revoke_login_key(sender_id, admin_only=True)
        if removed > 0:
            yield event.plain_result(
                f"🔒 已关闭管理员后台，{removed} 个管理员密钥已失效"
            )
        else:
            yield event.plain_result("ℹ️ 当前没有有效的管理员后台登录密钥")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        # 监听所有消息，智能识别是否为提醒意图并创建任务
        msg = event.message_str

        # 记录发送者最近一次 umo，方便按 user_tag 广播时找到会话
        try:
            self.task_manager.remember_user_umo(
                event.get_sender_id(), event.unified_msg_origin
            )
        except Exception:
            pass

        # 使用 LLM 判断是否为提醒意图
        if not await self._is_reminder_intent(msg, event):
            return

        sender_id = event.get_sender_id()

        # 使用 LLM 提取任务信息（含标签与目标 user_tag）
        task_info = await self._extract_task(msg, event)
        if task_info is None:
            return
        if not task_info.get("time"):
            yield event.plain_result("❌ 无法识别时间，请明确提醒时间")
            return

        content = task_info["content"]
        task_time = task_info["time"]
        task_tags = normalize_tags(task_info.get("tags"))
        target_user_tags = normalize_tags(task_info.get("target_user_tags"))

        # 按 user_tag 广播：为每个目标用户各建一份任务
        if target_user_tags:
            created_for = []
            skipped = []
            seen_targets: set[str] = set()
            for user_tag in target_user_tags:
                for user in self.task_manager.find_users_by_user_tag(user_tag):
                    target_sender = user["sender_id"]
                    if target_sender in seen_targets:
                        continue
                    seen_targets.add(target_sender)
                    if not user.get("umo"):
                        skipped.append(target_sender)
                        continue
                    tid = await self.task_manager.create_task(
                        sender_id=target_sender,
                        content=content,
                        task_time=task_time,
                        creator=sender_id,
                        umo=user["umo"],
                        tags=task_tags,
                    )
                    if tid:
                        created_for.append(target_sender)

            if not created_for:
                yield event.plain_result(
                    "❌ 未找到匹配标签 " + "、".join(target_user_tags) + " 的用户"
                )
                return

            reply = f"✅ 已按标签 {'、'.join(target_user_tags)} 创建 {len(created_for)} 个任务：{content}"
            if task_tags:
                reply += f"\n任务标签：{'、'.join(task_tags)}"
            if skipped:
                reply += f"\n⚠️ 跳过 {len(skipped)} 个未知会话的用户"
            yield event.plain_result(reply)
            return

        # 普通场景：为自己创建任务
        task_id = await self.task_manager.create_task(
            sender_id=sender_id,
            content=content,
            task_time=task_time,
            creator=sender_id,
            umo=event.unified_msg_origin,
            tags=task_tags,
        )

        if task_id:
            reply = f"✅ 任务已创建：{content}"
            if task_tags:
                reply += f"\n标签：{'、'.join(task_tags)}"
            yield event.plain_result(reply)
        else:
            yield event.plain_result("❌ 任务创建失败：时间可能已过期")

    async def _is_reminder_intent(self, msg: str, event: AstrMessageEvent) -> bool:
        # 使用 LLM 判断消息是否是设置提醒的意图
        try:
            provider_id = (
                self.schedule_detection_provider_id
                or await self.context.get_current_chat_provider_id(
                    umo=event.unified_msg_origin
                )
            )

            system_prompt = (
                "判断用户消息是否是在设定提醒、任务或日程安排。"
                "返回 true 或 false\n"
                "示例：\n"
                "消息：提醒我明天下午3点开会\n"
                "true\n"
                "消息：后天上午10点记得交报告\n"
                "true\n"
                "消息：安排下周一早上9点半的团队会议\n"
                "true\n"
                "消息：提醒我等下吃饭\n"
                "true\n"
                "消息：给所有二处的人下达任务，明天上午提交报告\n"
                "true\n"
                "消息：别忘了吃饭\n"
                "false\n"
                "消息：今天天气怎么样\n"
                "false\n"
                "消息：帮我查一下快递\n"
                "false\n"
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
            return "true" in text.lower()
        except Exception as e:
            logger.error(f"判断提醒意图失败: {e}")
            return False

    async def _extract_task(self, msg: str, event: AstrMessageEvent) -> dict | None:
        # 使用 LLM 从消息中提取任务内容、时间、标签和目标用户标签
        # 返回 {content, time, tags, target_user_tags}，解析失败返回 None
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
            next_monday = now + timedelta(days=(7 - now.weekday()))
            half_hour_later = now + timedelta(minutes=30)
            # 情人节示例：找下一个 2/14
            valentines = now.replace(
                month=2, day=14, hour=9, minute=0, second=0, microsecond=0
            )
            if valentines <= now:
                valentines = valentines.replace(year=now.year + 1)

            system_prompt = (
                f"你是一个日程解析助手。当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')}"
                f"（{weekday_name}，Asia/Shanghai）。\n\n"
                "从用户消息中提取提醒任务信息，返回严格的 JSON，字段如下：\n"
                "{\n"
                '  "content": "任务内容简述",\n'
                '  "date_str": "2026-07-11T15:00:00",\n'
                '  "tags": ["节日", "重要"],\n'
                '  "target_user_tags": ["二处"]\n'
                "}\n\n"
                "规则：\n"
                "- content：任务内容，简洁明了，不要包含标签或目标群体的描述。\n"
                "- date_str：提醒时间，ISO 格式（基于上方当前时间换算）。\n"
                "- 只指定日期时 date_str 用当天 09:00:00；完全没提时间用当前时间的半小时后。\n"
                "- 「明天」「后天」「下周一」「X小时后」等相对时间按当前时间换算成绝对日期。\n"
                "- 只说「周一」「周六」等，指从当前时间起最近一次即将到来的那个星期几。\n"
                "- 无法确定日期时 date_str 返回空字符串。\n"
                "- tags：任务本身的标签列表（例如「节日」「生日」「工作」）。用户显式用「标签：xxx」「打标签 xxx」「tag: xxx」等方式指明时必须提取。无标签则返回空数组。\n"
                "- target_user_tags：用户希望把任务下发给的“人群标签”。当消息包含「给所有 X 的人」「给带 X 标签的人」「让 X 组的人」等意图时提取，否则返回空数组。\n"
                "- 不要把 target_user_tags 里的词重复放进 tags。\n\n"
                "示例：\n"
                f"消息：提醒我明天下午3点开会\n"
                f'{{"content": "开会", "date_str": "{tomorrow.strftime("%Y-%m-%dT15:00:00")}", "tags": [], "target_user_tags": []}}\n\n'
                f"消息：提醒我情人节记得订花，标签：节日\n"
                f'{{"content": "订花", "date_str": "{valentines.strftime("%Y-%m-%dT09:00:00")}", "tags": ["节日"], "target_user_tags": []}}\n\n'
                f"消息：给所有二处的人下达任务，明天上午9点提交一份周报\n"
                f'{{"content": "提交一份周报", "date_str": "{tomorrow.strftime("%Y-%m-%dT09:00:00")}", "tags": [], "target_user_tags": ["二处"]}}\n\n'
                f"消息：周一提醒我去健身，打标签 健康\n"
                f'{{"content": "去健身", "date_str": "{next_monday.strftime("%Y-%m-%dT09:00:00")}", "tags": ["健康"], "target_user_tags": []}}\n\n'
                f"消息：提醒我买牛奶\n"
                f'{{"content": "买牛奶", "date_str": "{half_hour_later.strftime("%Y-%m-%dT%H:%M:%S")}", "tags": [], "target_user_tags": []}}\n\n'
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
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start == -1 or brace_end == -1:
                return None
            text = text[brace_start : brace_end + 1]

            result = json.loads(text)

            content = (result.get("content") or "").strip()
            date_str = (result.get("date_str") or "").strip()
            tags = normalize_tags(result.get("tags"))
            target_user_tags = normalize_tags(result.get("target_user_tags"))

            if not content:
                return None

            # 验证并标准化时间
            task_time = ""
            if date_str:
                try:
                    parsed = datetime.fromisoformat(date_str)
                    if 2024 <= parsed.year <= 2100:
                        task_time = parsed.isoformat()
                except (ValueError, TypeError):
                    try:
                        parsed = dateutil_parser.parse(date_str, fuzzy=True)
                        if parsed.year < 2024 or parsed.year > 2100:
                            parsed = parsed.replace(year=now.year)
                        task_time = parsed.isoformat()
                    except (ValueError, TypeError):
                        task_time = ""

            return {
                "content": content,
                "time": task_time,
                "tags": tags,
                "target_user_tags": target_user_tags,
            }

        except Exception as e:
            logger.error(f"提取任务失败: {e}")
            return None


class TaskManager:
    # 任务管理器：负责任务的持久化、定时调度、用户标签管理

    def __init__(self, users_dir: Path, user_tags_file: Path, context: Context):
        self.users_dir = users_dir
        self.user_tags_file = user_tags_file
        self.context = context
        self.active_timers: dict[
            str, asyncio.Task
        ] = {}  # 活跃定时器字典，只存未触发的任务
        # user_tags 结构：{sender_id: {umo: str, tags: [str]}}
        self._user_tags: dict = load_user_tags(user_tags_file)

    @staticmethod
    def _sanitize_id(raw: str) -> str:
        # 清洗 sender_id 中的非法文件名字符（兼容 Windows）
        for ch in ("<", ">", ":", '"', "/", "\\", "|", "?", "*"):
            raw = raw.replace(ch, "_")
        return raw

    def _task_file(self, sender_id: str) -> Path:
        # 获取指定用户的任务文件路径
        return self.users_dir / f"{self._sanitize_id(sender_id)}.json"

        # ---- 用户标签管理 ----

    def _persist_user_tags(self) -> None:
        save_user_tags(self.user_tags_file, self._user_tags)

    def remember_user_umo(self, sender_id: str, umo: str) -> None:
        # 记录用户最近的 umo，方便按标签广播时能找到会话
        sender_id = (sender_id or "").strip()
        umo = (umo or "").strip()
        if not sender_id or not umo:
            return
        entry = self._user_tags.get(sender_id)
        if entry is None:
            self._user_tags[sender_id] = {"umo": umo, "tags": []}
            self._persist_user_tags()
            return
        if entry.get("umo") != umo:
            entry["umo"] = umo
            self._persist_user_tags()

    def get_all_user_tags(self) -> dict:
        # 返回 user_tags 的副本
        return {
            sender_id: {
                "umo": entry.get("umo", ""),
                "tags": list(entry.get("tags", [])),
            }
            for sender_id, entry in self._user_tags.items()
        }

    def set_user_profile(
        self,
        sender_id: str,
        tags: list[str] | None = None,
        umo: str | None = None,
    ) -> dict:
        # 创建或更新用户资料，返回存储的条目
        sender_id = (sender_id or "").strip()
        if not sender_id:
            raise ValueError("sender_id 不能为空")
        entry = self._user_tags.get(sender_id) or {"umo": "", "tags": []}
        if tags is not None:
            entry["tags"] = normalize_tags(tags)
        if umo is not None:
            entry["umo"] = umo.strip()
        self._user_tags[sender_id] = entry
        self._persist_user_tags()
        return {
            "sender_id": sender_id,
            "umo": entry.get("umo", ""),
            "tags": list(entry.get("tags", [])),
        }

    def delete_user_profile(self, sender_id: str) -> bool:
        # 删除用户资料，返回是否删除成功
        if sender_id in self._user_tags:
            del self._user_tags[sender_id]
            self._persist_user_tags()
            return True
        return False

    def find_users_by_user_tag(self, tag: str) -> list[dict]:
        # 查找包含指定 user_tag 的所有用户
        return find_users_by_tag(self._user_tags, tag)

    # ---- 任务持久化 ----

    async def load_pending_tasks(self):
        # 加载所有未过期的待执行任务并启动定时器
        now = datetime.now()
        loaded = 0

        for task_file in self.users_dir.glob("*.json"):
            try:
                with open(task_file, encoding="utf-8") as f:
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

    async def get_tasks(self, sender_id: str) -> list[dict]:
        # 获取指定用户的任务列表，自动将已过期的未完成任务标记为已完成
        now = datetime.now()
        changed = False
        file = self._task_file(sender_id)
        if file.exists():
            with open(file, encoding="utf-8") as f:
                data = json.load(f)
                tasks = data.get("tasks", [])
                for task in tasks:
                    if not task.get("completed"):
                        try:
                            task_time = datetime.fromisoformat(task["time"])
                            if task_time <= now:
                                task["completed"] = True
                                changed = True
                        except Exception:
                            pass
                if changed:
                    with open(file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False)
                return tasks
        return []

    async def create_task(
        self,
        sender_id: str,
        content: str,
        task_time: str,
        creator: str,
        umo: str,
        tags: list[str] | None = None,
    ) -> str | None:
        # 创建新任务并启动定时器，返回任务 ID；时间过期或格式错误返回 None
        task_id = f"{sender_id}_{int(time.time() * 1000)}"

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
            "sender_id": sender_id,
            "time": task_time,
            "content": content,
            "creator": creator,
            "umo": umo,
            "tags": normalize_tags(tags),
            "created_at": datetime.now().isoformat(),
            "completed": False,
        }

        # 保存到文件
        file = self._task_file(sender_id)
        data = {"tasks": []}
        if file.exists():
            with open(file, encoding="utf-8") as f:
                data = json.load(f)

        data.setdefault("tasks", []).append(task)

        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        # 顺带记录一次 umo，方便后续按 user_tag 广播
        if umo:
            self.remember_user_umo(sender_id, umo)

        # 启动定时器
        await self.start_timer(task)

        return task_id

    async def update_task_tags(self, task_id: str, tags: list[str]) -> bool:
        # 更新单个任务的标签，返回是否更新成功
        normalized = normalize_tags(tags)
        for task_file in self.users_dir.glob("*.json"):
            try:
                with open(task_file, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            hit = False
            for t in data.get("tasks", []):
                if t.get("id") == task_id:
                    t["tags"] = normalized
                    hit = True
                    break
            if hit:
                with open(task_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                return True
        return False

    async def start_timer(self, task: dict):
        # 为任务启动定时提醒，到期后自动执行
        try:
            task_time = datetime.fromisoformat(task["time"])
            delay = (task_time - datetime.now()).total_seconds()

            if delay > 0:
                timer = asyncio.create_task(self._execute_task(task, delay))
                self.active_timers[task["id"]] = timer
        except Exception as e:
            logger.error(f"启动定时器失败: {e}")

    async def _execute_task(self, task: dict, delay: float):
        # 任务到期执行：发送提醒消息并标记完成
        await asyncio.sleep(delay)

        try:
            msg = f"⏰ 提醒：{task['content']}"
            if task.get("tags"):
                msg += "\n标签：" + "、".join(task["tags"])
            message_chain = MessageChain().message(msg)
            await self.context.send_message(task["umo"], message_chain)
            logger.info(f"任务执行: {task['content']}")
        except Exception as e:
            logger.error(f"发送提醒失败: {e}")

        self.active_timers.pop(task["id"], None)
        await self._mark_completed(task)

    async def _mark_completed(self, task: dict):
        # 将任务标记为已完成（持久化到文件）
        file = self._task_file(task["sender_id"])
        if file.exists():
            with open(file, encoding="utf-8") as f:
                data = json.load(f)

            for t in data.get("tasks", []):
                if t["id"] == task["id"]:
                    t["completed"] = True
                    break

            with open(file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

    async def clear_tasks(self, sender_id: str):
        # 清空指定用户的所有任务并取消相关定时器
        file = self._task_file(sender_id)
        if file.exists():
            with open(file, "w", encoding="utf-8") as f:
                json.dump({"tasks": []}, f, ensure_ascii=False)

        to_cancel = [tid for tid in self.active_timers if tid.startswith(sender_id)]
        for tid in to_cancel:
            self.active_timers[tid].cancel()
            del self.active_timers[tid]
