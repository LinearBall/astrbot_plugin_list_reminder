import asyncio
import secrets
from datetime import datetime
from typing import Dict, List

import hypercorn.asyncio
from astrbot.api import logger
from hypercorn.config import Config
from quart import Quart, jsonify, redirect, render_template, request, session, url_for

from db import Task

from .shared_types import LoginPayload
from .task_manager_new import TaskManagerNew

APP = Quart(__name__)
# Runtime state, configured in start_server()
TASK_MANAGER: TaskManagerNew | None = None
# Active per-user login keys. Format = {key: sender_id}
LOGIN_KEYS: Dict[str, str] = dict()


def set_task_manager(task_manager):
    """Keep a reference to the plugin TaskManager (called from main.py)."""
    global TASK_MANAGER
    TASK_MANAGER = task_manager


def issue_login_key(sender_id: str) -> str:
    """Generate a login key bound to a specific user.

    Args:
        sender_id: The user this key belongs to.

    Returns:
        The generated key string.
    """
    key = secrets.token_urlsafe(16)
    LOGIN_KEYS[key] = sender_id
    return key


def current_session_sender_id() -> str | None:
    """
    检查当前session的`login_key`字段。
    若有值且该值已映射到sender_id，则返回sender_id；
    否则，返回None。Return the user bound to the current session, or None if invalid.
    """
    key = session.get("login_key")
    if not key or key not in LOGIN_KEYS:
        session.clear()
        return None
    return LOGIN_KEYS[key]


# --- Auth ---

PUBLIC_ENDPOINTS = {"health_check", "login", "static"}
PUBLIC_API_ENDPOINTS = {"api_health", "api_login", "api_logout"}


def __make_json_response(code: int, **payload):
    """Unified API envelope: {"code": int, "payload": {...}}."""
    return jsonify({"code": code, "payload": payload})


def api_success(**payload):
    return __make_json_response(200, **payload)


def api_error(code: int, message: str, **extra):
    """Return a unified error response with a matching HTTP status."""
    return __make_json_response(code, message=message, **extra), code


@APP.before_request
async def check_if_logged_in():
    if current_session_sender_id():
        return None
    if request.path.startswith("/api/"):
        if request.endpoint in PUBLIC_API_ENDPOINTS:
            return None
        return api_error(401, "未登录")
    if request.endpoint not in PUBLIC_ENDPOINTS:
        return redirect(url_for("login"))
    return None


# --- Routes ---


@APP.route("/health")
async def health_check():
    return api_success(status="running")


@APP.route("/api/health", methods=["GET"])
async def api_health():
    return api_success(status="running")


@APP.route("/login", methods=["GET", "POST"])
async def login():
    if current_session_sender_id():
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        form = await request.form
        if form.get("key") in LOGIN_KEYS:
            session["login_key"] = form.get("key")
            return redirect(url_for("index"))
        error = "密钥错误，请重试。"
    return await render_template("login.html", error=error)


@APP.route("/logout", methods=["POST"])
async def logout():
    session.clear()
    return redirect(url_for("login"))


@APP.route("/")
async def index():
    return await render_template("index.html")


# --- API ---


@APP.route("/api/login", methods=["POST"])
async def api_login():
    sender_id = current_session_sender_id()
    if sender_id:
        return api_success(message="已登录", sender_id=sender_id)

    data: LoginPayload = await request.get_json(silent=True)
    key: str = (data.get("key") or "").strip()
    if not key:
        return api_error(400, "请提供登录密钥")
    if key not in LOGIN_KEYS:
        return api_error(401, "密钥错误，请重试。")

    session["login_key"] = key
    return api_success(message="登录成功", sender_id=LOGIN_KEYS[key])


@APP.route("/api/logout", methods=["POST"])
async def api_logout():
    session.clear()
    return api_success(message="已退出登录")


@APP.route("/api/me", methods=["GET"])
async def api_me():
    """
    通过确定当前session中记录的`login_key`，来确认当前登陆的用户（sender_id）是谁"""
    sender_id = current_session_sender_id()
    if not sender_id:
        return api_error(401, "未登录")
    return api_success(sender_id=sender_id)


@APP.route("/api/tasks", methods=["GET"])
async def list_tasks():
    """
    获取当前登陆用户的所有任务。
    任务按到期时间排序，最早到期在前。
    """
    global TASK_MANAGER
    tm = TASK_MANAGER
    if tm is None:
        return api_error(503, "任务管理器不可用")
    sender_id = current_session_sender_id()
    if not sender_id:
        return api_error(401, "未登录")
    tasks: List[Task] = tm.db.get_tasks_by_creator(sender_id)
    tasks.sort(key=lambda t: t.due_time)
    return api_success(tasks=[t.model_dump() for t in tasks])


@APP.route("/api/tasks", methods=["POST"])
async def create_task():
    tm = TASK_MANAGER
    if tm is None:
        return api_error(503, "任务管理器不可用")
    sender_id = current_session_sender_id()
    if not sender_id:
        return api_error(401, "未登录")

    data: Task = await request.get_json(silent=True)  # todo: 规范数据格式
    content = data.content.strip()
    due_time = data.due_time
    umo = data.umo.strip()

    if not content or not due_time or not umo:
        return api_error(400, "内容、时间、umo 不能为空")

    try:
        task_id = tm.create_task(
            creator=sender_id,
            umo=umo,
            content=content,
            due_time=due_time,
        )
    except Exception as e:
        logger.error(f"WebUI 创建任务失败: {e}")
        return api_error(500, f"创建失败: {e}")

    return api_success(message="任务创建成功", task_id=task_id)


@APP.route("/api/tasks/<int:task_id>", methods=["DELETE"])
async def delete_task(task_id):
    tm = TASK_MANAGER
    if tm is None:
        return api_error(503, "任务管理器不可用")
    sender_id = current_session_sender_id()
    if not sender_id:
        return api_error(401, "未登录")

    task = tm.db.get_task_by_id(task_id)
    if not task or task.creator != sender_id:
        return api_error(404, "任务未找到或无权限")

    tm.db.delete_task(task_id)
    timer = tm.active_timers.pop(task_id, None)
    if timer and not timer.done():
        timer.cancel()
    return api_success(message="任务已删除")


# --- Server lifecycle ---


async def start_server(config=None, task_manager=None):
    global TASK_MANAGER
    config = config or {}
    port = config.get("webui_port", 5001)
    if task_manager is not None:
        TASK_MANAGER = task_manager
    APP.secret_key = secrets.token_urlsafe(32)

    hypercorn_config = Config()
    hypercorn_config.bind = [f"0.0.0.0:{port}"]
    hypercorn_config.graceful_timeout = 5

    # Provide a shutdown trigger so hypercorn skips its signal-handler
    # setup, which crashes in a non-main thread on Windows.
    shutdown_event = asyncio.Event()
    await hypercorn.asyncio.serve(
        APP, hypercorn_config, shutdown_trigger=shutdown_event.wait
    )
