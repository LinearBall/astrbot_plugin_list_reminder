import asyncio
import json
import secrets
from datetime import datetime
from pathlib import Path

import hypercorn.asyncio
from hypercorn.config import Config
from quart import (
    Quart,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from astrbot.api import logger

from .config import GROUPS_DIR, USERS_DIR

app = Quart(__name__)

# Runtime state, configured in start_server()
SERVER_LOGIN_KEY = None
_task_manager = None


def set_task_manager(task_manager):
    """Keep a reference to the plugin TaskManager (called from main.py)."""
    global _task_manager
    _task_manager = task_manager


# --- Task file helpers (read/write per request, no caching) ---


def _task_file(is_group: bool, target_id: str) -> Path:
    name = f"group_{target_id}.json" if is_group else f"user_{target_id}.json"
    return (GROUPS_DIR if is_group else USERS_DIR) / name


def _load_tasks(file_path: Path) -> list:
    if not file_path.exists():
        return []
    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f).get("tasks", [])
    except Exception:
        return []


def _save_tasks(file_path: Path, tasks: list) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump({"tasks": tasks}, f, ensure_ascii=False)


def _iter_all_tasks():
    """Yield (task, is_group) for every task stored on disk."""
    for file_path in USERS_DIR.glob("user_*.json"):
        for task in _load_tasks(file_path):
            yield task, False
    for file_path in GROUPS_DIR.glob("group_*.json"):
        for task in _load_tasks(file_path):
            yield task, True


def _cancel_timer(task_id: str) -> None:
    """Cancel an active timer in the TaskManager if present."""
    tm = _task_manager
    if not tm:
        return
    timer = tm.active_timers.pop(task_id, None)
    if timer and not timer.done():
        timer.cancel()


# --- Auth ---

PUBLIC_ENDPOINTS = {"health_check", "login", "static"}


@app.before_request
async def require_login():
    if session.get("authenticated"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "message": "未登录"}), 401
    if request.endpoint not in PUBLIC_ENDPOINTS:
        return redirect(url_for("login"))


# --- Routes ---


@app.route("/health")
async def health_check():
    return jsonify({"status": "running"})


@app.route("/login", methods=["GET", "POST"])
async def login():
    if session.get("authenticated"):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        form = await request.form
        if form.get("key") == SERVER_LOGIN_KEY:
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "密钥错误，请重试。"
    return await render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
async def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
async def index():
    return await render_template("index.html")


# --- API ---


@app.route("/api/tasks", methods=["GET"])
async def list_tasks():
    user_tasks = []
    group_tasks = []
    for task, is_group in _iter_all_tasks():
        item = {
            "task_id": task.get("id"),
            "type": "group" if is_group else "user",
            "target_id": task.get("target_id"),
            "umo": task.get("umo", ""),
            "content": task.get("content", ""),
            "time": task.get("time", ""),
            "completed": bool(task.get("completed", False)),
            "creator": task.get("creator", ""),
        }
        if is_group:
            group_tasks.append(item)
        else:
            user_tasks.append(item)
    user_tasks.sort(key=lambda x: x["time"])
    group_tasks.sort(key=lambda x: x["time"])
    return jsonify({"user_tasks": user_tasks, "group_tasks": group_tasks})


@app.route("/api/tasks", methods=["POST"])
async def create_task():
    tm = _task_manager
    if tm is None:
        return jsonify(
            {
                "success": False,
                "message": "TaskManager 不可用，无法创建会执行的提醒任务",
            }
        ), 503

    data = await request.get_json() or {}
    task_type = (data.get("type") or "").strip()
    target_id = (data.get("target_id") or "").strip()
    umo = (data.get("umo") or "").strip()
    content = (data.get("content") or "").strip()
    task_time = (data.get("time") or "").strip()

    if task_type not in ("user", "group"):
        return jsonify({"success": False, "message": "type 必须为 user 或 group"})
    if not target_id or not content or not task_time:
        return jsonify(
            {"success": False, "message": "target_id、content、time 不能为空"}
        )

    is_group = task_type == "group"
    if is_group:
        if not umo:
            return jsonify(
                {"success": False, "message": "群组任务必须填写完整 session_id (umo)"}
            )
        if ":" not in umo:
            return jsonify(
                {
                    "success": False,
                    "message": "群组任务的 session_id 需包含平台前缀（如 aiocqhttp:GroupMessage:...）",
                }
            )
    else:
        umo = umo or target_id

    # Normalize datetime-local input (e.g. 2024-01-01T15:00) to ISO with seconds.
    if "T" in task_time and task_time.count(":") == 1:
        task_time += ":00"
    try:
        datetime.fromisoformat(task_time)
    except Exception:
        return jsonify(
            {"success": False, "message": "时间格式错误，请使用 YYYY-MM-DDTHH:MM:SS"}
        )

    try:
        task_id = await tm.create_task(
            target_id=target_id,
            is_group=is_group,
            content=content,
            task_time=task_time,
            creator="webui",
            umo=umo,
        )
    except Exception as e:
        logger.error(f"WebUI 创建任务失败: {e}")
        return jsonify({"success": False, "message": f"创建失败: {e}"})

    if not task_id:
        return jsonify(
            {"success": False, "message": "创建失败：提醒时间可能已过期或格式无效"}
        )
    return jsonify({"success": True, "message": "任务创建成功", "task_id": task_id})


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
async def delete_task(task_id):
    for task, is_group in _iter_all_tasks():
        if task.get("id") == task_id:
            file_path = _task_file(is_group, task.get("target_id", ""))
            tasks = _load_tasks(file_path)
            tasks = [t for t in tasks if t.get("id") != task_id]
            _save_tasks(file_path, tasks)
            _cancel_timer(task_id)
            return jsonify({"success": True, "message": "任务已删除"})
    return jsonify({"success": False, "message": "任务未找到"}), 404


# --- Server lifecycle ---


def run_server(config, task_manager=None):
    asyncio.run(start_server(config, task_manager))


async def start_server(config=None, task_manager=None):
    global SERVER_LOGIN_KEY, _task_manager
    config = config or {}
    port = config.get("webui_port", 5001)
    SERVER_LOGIN_KEY = config.get("server_key") or secrets.token_urlsafe(16)
    if not config.get("server_key"):
        logger.info(f"自动生成的WebUI登录密钥: {SERVER_LOGIN_KEY}")
    if task_manager is not None:
        _task_manager = task_manager
    app.secret_key = secrets.token_urlsafe(32)

    hypercorn_config = Config()
    hypercorn_config.bind = [f"0.0.0.0:{port}"]
    hypercorn_config.graceful_timeout = 5

    # Provide a shutdown trigger so hypercorn skips its signal-handler
    # setup, which crashes in a non-main thread on Windows.
    shutdown_event = asyncio.Event()
    await hypercorn.asyncio.serve(
        app, hypercorn_config, shutdown_trigger=shutdown_event.wait
    )
