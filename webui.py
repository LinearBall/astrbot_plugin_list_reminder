import asyncio
import secrets
from datetime import datetime

import hypercorn.asyncio
from hypercorn.config import Config
from quart import Quart, jsonify, redirect, render_template, request, session, url_for

from astrbot.api import logger

from .task_manager_new import TaskManagerNew

APP = Quart(__name__)
# Runtime state, configured in start_server()
TASK_MANAGER: TaskManagerNew | None = None
# Active per-user login keys: {key: {"sender_id": str}}
LOGIN_KEYS: dict[str, dict] = {}


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
    LOGIN_KEYS[key] = {"sender_id": sender_id}
    return key


def current_session_sender_id() -> str | None:
    """Return the user bound to the current session, or None if invalid.

    Every request re-validates against the live key dict, so a revoked key
    immediately invalidates existing sessions.
    """
    key = session.get("login_key")
    if not key or key not in LOGIN_KEYS:
        session.clear()
        return None
    return LOGIN_KEYS[key]["sender_id"]


# --- Auth ---

PUBLIC_ENDPOINTS = {"health_check", "login", "static"}


class RespTemplate(dict):
    def __init__(self, code: int, **kwargs):
        super().__init__()
        self.code = code
        self.payload = kwargs

    def to_dict(self):
        return {"code": self.code, "payload": self.payload}


@APP.before_request
async def check_if_logged_in():
    if current_session_sender_id():
        return None
    elif request.path.startswith("/api/"):
        # return jsonify({"code": 401, "payload": {"message": "未登录"}})
        return jsonify(RespTemplate(401, message="未登录").to_dict())
    elif request.endpoint not in PUBLIC_ENDPOINTS:
        return redirect(url_for("login"))
    return None


# --- Routes ---


@APP.route("/health")
async def health_check():
    return jsonify(RespTemplate(200, status="running").to_dict())


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


def _serialize_task(task) -> dict:
    due = datetime.fromtimestamp(task.due_time)
    return {
        "task_id": task.task_id,
        "creator": task.creator,
        "umo": task.umo,
        "content": task.content,
        "time": due.strftime("%Y-%m-%dT%H:%M:%S"),
        "completed": bool(task.completed),
    }


# --- API ---


@APP.route("/api/tasks", methods=["GET"])
async def list_tasks():
    tm = TASK_MANAGER
    if tm is None:
        return jsonify({"tasks": []})
    sender_id = current_session_sender_id()
    if not sender_id:
        return jsonify(RespTemplate(401, message="未登录").to_dict())
    tasks = tm.db.get_tasks_by_creator(sender_id)
    tasks.sort(key=lambda t: t.due_time)
    return jsonify({"tasks": [_serialize_task(t) for t in tasks]})


@APP.route("/api/tasks", methods=["POST"])
async def create_task():
    tm = TASK_MANAGER
    if tm is None:
        return (jsonify({"success": False, "message": "任务管理器不可用"}), 503)
    sender_id = current_session_sender_id()
    if not sender_id:
        return jsonify(RespTemplate(401, message="未登录").to_dict())

    data = await request.get_json() or {}
    content = (data.get("content") or "").strip()
    task_time = (data.get("time") or "").strip()
    umo = (data.get("umo") or "").strip()

    if not content or not task_time or not umo:
        return jsonify({"success": False, "message": "内容、时间、umo 不能为空"})

    # Normalize datetime-local input (e.g. 2024-01-01T15:00) to ISO with seconds.
    if "T" in task_time and task_time.count(":") == 1:
        task_time += ":00"
    try:
        due = datetime.fromisoformat(task_time).timestamp()
    except Exception:
        return jsonify(
            {"success": False, "message": "时间格式错误，请使用 YYYY-MM-DDTHH:MM"}
        )

    try:
        task_id = tm.create_task(
            creator=sender_id,
            umo=umo,
            content=content,
            due_time=due,
        )
    except Exception as e:
        logger.error(f"WebUI 创建任务失败: {e}")
        return jsonify({"success": False, "message": f"创建失败: {e}"})

    return jsonify({"success": True, "message": "任务创建成功", "task_id": task_id})


@APP.route("/api/tasks/<int:task_id>", methods=["DELETE"])
async def delete_task(task_id):
    tm = TASK_MANAGER
    if tm is None:
        return (jsonify({"success": False, "message": "任务管理器不可用"}), 503)
    sender_id = current_session_sender_id()
    if not sender_id:
        return jsonify(RespTemplate(401, message="未登录").to_dict())

    task = tm.db.get_task_by_id(task_id)
    if not task or task.creator != sender_id:
        return jsonify({"success": False, "message": "任务未找到或无权限"}), 404

    tm.db.delete_task(task_id)
    timer = tm.active_timers.pop(task_id, None)
    if timer and not timer.done():
        timer.cancel()
    return jsonify({"success": True, "message": "任务已删除"})


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
