import asyncio
import secrets
from pathlib import Path
from typing import Dict, List

import hypercorn.asyncio
import pydantic
from astrbot.api import logger
from hypercorn.config import Config
from quart import Quart, jsonify, request, send_from_directory, session

from .db import EditTaskPayload, Task
from .shared_types import LoginPayload
from .todo_manager import TodoManager

DIST_DIR = Path(__file__).parent / "dist"
PUBLIC_ENDPOINTS = {"health_check", "login", "static"}
PUBLIC_API_ENDPOINTS = {"api_health", "api_login", "api_logout", "api_me"}


def __make_json_response(code: int, **payload):
    """Unified API envelope: {"code": int, "payload": {...}}."""
    return jsonify({"code": code, "payload": payload})


def api_success(**payload):
    return __make_json_response(200, **payload)


def api_error(code: int, message: str, **extra):
    """Return a unified error response with a matching HTTP status."""
    return __make_json_response(code, message=message, **extra), code


class WebUIServer:
    def __init__(self, tm: TodoManager) -> None:
        self.tm = tm
        self.app = Quart(__name__)
        self.login_keys: Dict[str, str] = dict()
        self.sender_id_2_umo: Dict[str, str] = dict()

        self.init_before_request()
        self.init_routes()
        self.init_apis()

    def issue_login_key(self, sender_id: str) -> str:
        """生成login key，并绑定到指定用户。

        Args:
            sender_id: The user this key belongs to.

        Returns:
            The generated key string.
        """
        key = secrets.token_urlsafe(16)
        self.login_keys[key] = sender_id
        return key

    def register_umo_to_sender(self, sender_id: str, umo_id: str):
        """将sender_id绑定到umo_id。

        Args:
            sender_id: 用户ID。
            umo_id: UMO ID。
        """
        self.sender_id_2_umo[sender_id] = umo_id

    def current_session_sender_id(self) -> str | None:
        """
        检查当前session的`login_key`字段。
        若有值且该值已映射到sender_id，则返回sender_id；
        否则，返回None。Return the user bound to the current session, or None if invalid.
        """
        key = session.get("login_key")
        if not key or key not in self.login_keys:
            session.clear()
            return None
        return self.login_keys[key]

    # --- Auth ---
    def init_before_request(self):
        @self.app.before_request
        async def check_if_logged_in():
            # 1. 允许放行已有登录会话的用户
            if self.current_session_sender_id():
                return None
            # 2. 区分api访问和原版访问
            if request.path.startswith("/api/"):
                if request.endpoint in PUBLIC_API_ENDPOINTS:
                    return None
                return api_error(401, "未登录！")
            return None

    # --- Routes ---
    def init_routes(self):
        @self.app.route("/", defaults={"pp": ""})
        @self.app.route("/<path:pp>")
        # async def index():
        #     return await render_template("index.html")
        async def serve_vue_spa(pp: str):
            if pp.startswith("api/"):
                # 没有被其他/api/...路由走，说明这个接口不存在
                return api_error(404, "接口不存在")
            target_file = DIST_DIR / pp
            if pp != "" and target_file.exists() and target_file.is_file():
                # 说明访问的是某个文件
                return await send_from_directory(DIST_DIR, pp)
            else:
                # 否则重定向到首页
                return await send_from_directory(DIST_DIR, "index.html")

    # --- API ---
    def init_apis(self):
        @self.app.route("/api/health", methods=["GET"])
        async def api_health():
            return api_success(status="running")

        @self.app.route("/api/login", methods=["POST"])
        async def api_login():
            sender_id = self.current_session_sender_id()
            if sender_id:
                return api_success(message="已登录", sender_id=sender_id)

            data: LoginPayload = await request.get_json(silent=True)
            key: str = (data.get("key") or "").strip()
            if not key:
                return api_error(400, "请提供登录密钥")
            if key not in self.login_keys:
                return api_error(401, "密钥错误，请重试。")

            session["login_key"] = key
            return api_success(message="登录成功", sender_id=self.login_keys[key])

        @self.app.route("/api/logout", methods=["POST"])
        async def api_logout():
            session.clear()
            return api_success(message="已退出登录")

        @self.app.route("/api/me", methods=["GET"])
        async def api_me():
            """
            通过确定当前session中记录的`login_key`，来确认当前登陆的用户（sender_id）是谁"""
            sender_id = self.current_session_sender_id()
            if not sender_id:
                return api_error(401, "未登录")
            return api_success(sender_id=sender_id)

        @self.app.route("/api/tasks", methods=["GET"])
        async def list_tasks():
            """
            获取当前登陆用户的所有任务。
            任务按到期时间排序，最早到期在前。
            """
            sender_id = self.current_session_sender_id()
            if not sender_id:
                return api_error(401, "未登录")
            tasks: List[Task] = self.tm.db.get_tasks_by_creator(sender_id)
            tasks.sort(key=lambda t: t.due_time)
            return api_success(tasks=[t.model_dump() for t in tasks])

        @self.app.route("/api/tasks", methods=["POST"])
        async def create_task():
            sender_id = self.current_session_sender_id()
            if not sender_id:
                return api_error(401, "未登录")

            # 尝试获取前端传来的数据，并进行检验
            try:
                data: EditTaskPayload = await request.get_json(silent=True)
            except pydantic.ValidationError:
                return api_error(400, "内容、时间、umo 不能为空")
            content = data["content"].strip()
            due_time = data["due_time"]
            completed = data["completed"]

            task_id = self.tm.create_task(
                creator=sender_id,
                umo=self.sender_id_2_umo[sender_id],
                content=content,
                due_time=due_time,
                completed=completed,
            )
            if task_id == -1:
                logger.error(f"WebUI 创建任务失败：任务到期时间太早")
                return api_error(500, f"创建失败：任务到期时间太早")

            return api_success(message="任务创建成功", task_id=task_id)

        @self.app.route("/api/tasks/<int:task_id>", methods=["PUT"])
        async def update_task(task_id):
            sender_id = self.current_session_sender_id()
            if not sender_id:
                return api_error(401, "未登录")

            data: EditTaskPayload = await request.get_json(silent=True)
            content = data["content"]
            due_time = data["due_time"]
            completed = data["completed"]
            if not content or not due_time:
                return api_error(400, "内容、到期时间不能为空")

            task = self.tm.db.get_task_by_id(task_id)
            if not task or task.creator != sender_id:
                return api_error(404, "任务未找到或无权限")
            updated_task_id = self.tm.update_task(task_id, content, due_time, completed)
            if updated_task_id == -1:
                return api_error(500, "更新失败：任务不存在")

            return api_success(message="任务已更新", task_id=updated_task_id)

        @self.app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
        async def delete_task(task_id):
            sender_id = self.current_session_sender_id()
            if not sender_id:
                return api_error(401, "未登录")

            task = self.tm.db.get_task_by_id(task_id)
            if not task or task.creator != sender_id:
                return api_error(404, "任务未找到或无权限")

            self.tm.db.delete_task(task_id)
            timer = self.tm.active_timers.pop(task_id, None)
            if timer and not timer.done():
                timer.cancel()
            return api_success(message="任务已删除")

        # --- Server lifecycle ---
        async def start_server(port: int = 5001):
            self.app.secret_key = secrets.token_urlsafe(
                32
            )  # 听说是用于session加密的密钥

            hypercorn_config = Config()
            hypercorn_config.bind = [f"0.0.0.0:{port}"]
            hypercorn_config.graceful_timeout = 5

            # Provide a shutdown trigger so hypercorn skips its signal-handler
            # setup, which crashes in a non-main thread on Windows.
            shutdown_event = asyncio.Event()
            await hypercorn.asyncio.serve(
                self.app, hypercorn_config, shutdown_trigger=shutdown_event.wait
            )
