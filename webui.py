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

from .config import USERS_DIR
from .tag_utils import normalize_tags, task_has_any_tag

app = Quart(__name__)

# Runtime state
_task_manager = None
# Active login keys: {key: {"sender_id": str, "is_admin": bool, "issued_at": str}}
_login_keys: dict[str, dict] = {}
_shutdown_event: asyncio.Event | None = None


def set_task_manager(task_manager):
    """Set the TaskManager reference (called from main.py)."""
    global _task_manager
    _task_manager = task_manager


def get_access_urls(port: int, public_ip: str = "") -> list[tuple[str, str]]:
    """获取 WebUI 访问地址列表，每个元素为 (标签, URL)。

    规则：
    - 一定包含 localhost 内网地址。
    - 优先使用配置里的公网 IP；如果没配置就尝试调用第三方接口自动探测。
    - 探测失败也不报错，只返回 localhost。

    Args:
        port: WebUI 监听的端口。
        public_ip: 手动填写的公网 IP，留空则自动探测。

    Returns:
        列表，每项为 (显示标签, 完整 URL)。
    """
    # 先放内网（本机）地址
    results: list[tuple[str, str]] = [
        ("内网地址", f"http://localhost:{port}"),
    ]

    ip = (public_ip or "").strip()  # 公网地址

    # 没填公网 IP 就尝试自动探测
    if not ip:
        import socket

        old_timeout = socket.getdefaulttimeout()
        try:
            import urllib.request

            # 全局 socket 超时 2 秒，确保 DNS + 请求都不会卡太久
            socket.setdefaulttimeout(2)
            req = urllib.request.Request(
                "https://api.ipify.org",
                headers={"User-Agent": "astrbot-list-reminder"},
            )
            with urllib.request.urlopen(req) as resp:
                ip = resp.read().decode("utf-8").strip()
        except Exception:
            # 探测失败就跳过，不影响使用
            pass
        finally:
            socket.setdefaulttimeout(old_timeout)

    if ip:
        results.append(("公网地址", f"http://{ip}:{port}"))

    return results


def issue_login_key(sender_id: str, is_admin: bool = False) -> str:
    """生成绑定指定用户身份的登录密钥。

    Args:
        sender_id: 密钥归属的用户 sender_id。
        is_admin: 是否为管理员权限。

    Returns:
        生成的密钥字符串。
    """
    key = secrets.token_urlsafe(16)
    _login_keys[key] = {
        "sender_id": sender_id,
        "is_admin": bool(is_admin),
        "issued_at": datetime.now().isoformat(),
    }
    return key


def revoke_login_key(sender_id: str, admin_only: bool | None = None) -> int:
    """撤销指定用户的登录密钥。

    Args:
        sender_id: 要撤销密钥的用户 sender_id。
        admin_only: None = 撤销全部；True = 仅撤销管理员密钥；
            False = 仅撤销普通用户密钥。

    Returns:
        被撤销的密钥数量。
    """
    removed = 0
    for key in list(_login_keys.keys()):
        info = _login_keys[key]
        if info["sender_id"] != sender_id:
            continue
        if admin_only is True and not info["is_admin"]:
            continue
        if admin_only is False and info["is_admin"]:
            continue
        del _login_keys[key]
        removed += 1  # 删除密钥数量
    return removed


def _current_identity() -> dict | None:
    """如果当前 session 的登录密钥仍然有效，返回对应身份；否则返回 None。

    每次请求都会实时校验密钥字典，因此“关闭后台”（撤销密钥）
    会立即使已有会话失效。
    """
    key = session.get("login_key")
    if not key or key not in _login_keys:
        session.clear()
        return None
    info = _login_keys[key]
    return {
        "sender_id": info["sender_id"],
        "is_admin": info["is_admin"],
    }


# --- Task file helpers (read/write per request, no caching) ---


def _task_file(sender_id: str) -> Path:
    """Get the task file path for a sender_id (sanitized)."""
    safe = sender_id
    for ch in ("<", ">", ":", '"', "/", "\\", "|", "?", "*"):
        safe = safe.replace(ch, "_")
    return USERS_DIR / f"{safe}.json"


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
    """Yield every task stored on disk."""
    for file_path in USERS_DIR.glob("*.json"):
        yield from _load_tasks(file_path)


def _serialize_task(task: dict) -> dict:
    return {
        "task_id": task.get("id"),
        "sender_id": task.get("sender_id", ""),
        "umo": task.get("umo", ""),
        "content": task.get("content", ""),
        "time": task.get("time", ""),
        "completed": bool(task.get("completed", False)),
        "creator": task.get("creator", ""),
        "tags": list(task.get("tags", []) or []),
    }


def _cancel_timer(task_id: str) -> None:
    """Cancel an active timer in the TaskManager if present."""
    tm = _task_manager
    if not tm:
        return
    timer = tm.active_timers.pop(task_id, None)
    if timer and not timer.done():
        timer.cancel()


def _delete_task_by_id(task_id: str, identity: dict | None) -> bool:
    """Remove a task. Returns True on success. Non-admin can only delete own tasks."""
    for task in _iter_all_tasks():
        if task.get("id") != task_id:
            continue
        if identity and not identity["is_admin"]:
            if task.get("sender_id") != identity["sender_id"]:
                return False
        file_path = _task_file(task.get("sender_id", ""))
        remaining = [t for t in _load_tasks(file_path) if t.get("id") != task_id]
        _save_tasks(file_path, remaining)
        _cancel_timer(task_id)
        return True
    return False


# --- Auth ---

PUBLIC_ENDPOINTS = {"health_check", "login", "logout", "static"}


@app.before_request
async def require_login():
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if _current_identity() is not None:
        return None
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "message": "未登录"}), 401
    return redirect(url_for("login"))


# --- Routes ---


@app.route("/health")
async def health_check():
    return jsonify({"status": "running"})


@app.route("/login", methods=["GET", "POST"])
async def login():
    """Login page. Supports both form POST and ?key=xxx URL param."""
    error = None

    # 支持通过 URL 中的 ?key=xxx 参数直接登录（用户点击聊天里的链接时使用）。
    if request.method == "GET":
        key_from_url = (request.args.get("key") or "").strip()
        if key_from_url and key_from_url in _login_keys:
            session.clear()
            session["login_key"] = key_from_url
            return redirect(url_for("index"))

    if request.method == "POST":
        form = await request.form
        key = (form.get("key") or "").strip()
        if key and key in _login_keys:
            session.clear()
            session["login_key"] = key
            return redirect(url_for("index"))
        error = "密钥错误或已失效，请重试。"

    return await render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
async def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
async def index():
    return await render_template("index.html")


@app.route("/api/me", methods=["GET"])
async def me():
    ident = _current_identity()
    if not ident:
        return jsonify({"success": False, "message": "未登录"}), 401
    return jsonify(
        {
            "success": True,
            "sender_id": ident["sender_id"],
            "is_admin": ident["is_admin"],
        }
    )


@app.route("/api/logout", methods=["POST"])
async def api_logout():
    session.clear()
    return jsonify({"success": True, "message": "已退出登录"})


# --- Task API ---


def _task_matches_query(task: dict, query: str) -> bool:
    """Return True if task content or id contains the query (case-insensitive)."""
    if not query:
        return True
    q = query.lower()
    if q in (task.get("content") or "").lower():
        return True
    if q in (task.get("id") or "").lower():
        return True
    return False


@app.route("/api/tasks", methods=["GET"])
async def list_tasks():
    """列出当前身份可见的任务。

    查询参数：tag（可重复）、q（关键字搜索）、sender_id（仅管理员可用）、
    completed（"true"/"false"，按完成状态过滤）。
    """
    ident = _current_identity()
    if not ident:
        return jsonify({"success": False, "message": "未登录"}), 401

    args = request.args
    filter_tags = normalize_tags(args.getlist("tag"))
    query = (args.get("q") or "").strip()
    sender_filter = args.get("sender_id") or ""
    completed_filter = args.get("completed")

    if not ident["is_admin"]:
        sender_filter = ident["sender_id"]

    tasks = []
    for task in _iter_all_tasks():
        if sender_filter and task.get("sender_id") != sender_filter:
            continue
        if filter_tags and not task_has_any_tag(task, filter_tags):
            continue
        if not _task_matches_query(task, query):
            continue
        if completed_filter == "true" and not task.get("completed"):
            continue
        if completed_filter == "false" and task.get("completed"):
            continue
        tasks.append(_serialize_task(task))
    tasks.sort(key=lambda x: x["time"])
    return jsonify({"tasks": tasks})


@app.route("/api/tasks", methods=["POST"])
async def create_task():
    tm = _task_manager
    if tm is None:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "TaskManager 不可用，无法创建会执行的提醒任务",
                }
            ),
            503,
        )

    ident = _current_identity()
    if not ident:
        return jsonify({"success": False, "message": "未登录"}), 401

    data = await request.get_json() or {}
    sender_id = (data.get("sender_id") or "").strip()
    umo = (data.get("umo") or "").strip()
    content = (data.get("content") or "").strip()
    task_time = (data.get("time") or "").strip()
    tags = normalize_tags(data.get("tags"))

    if not ident["is_admin"]:
        sender_id = ident["sender_id"]
        profile = tm.get_all_user_tags().get(sender_id, {})
        if not umo:
            umo = profile.get("umo", "")

    if not sender_id or not umo or not content or not task_time:
        return jsonify(
            {"success": False, "message": "sender_id、umo、content、time 均为必填"}
        )

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
            sender_id=sender_id,
            content=content,
            task_time=task_time,
            creator=ident["sender_id"]
            + ("(webui-admin)" if ident["is_admin"] else "(webui)"),
            umo=umo,
            tags=tags,
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
    ident = _current_identity()
    if not ident:
        return jsonify({"success": False, "message": "未登录"}), 401
    if _delete_task_by_id(task_id, ident):
        return jsonify({"success": True, "message": "任务已删除"})
    return jsonify({"success": False, "message": "任务未找到或无权限"}), 404


@app.route("/api/tasks/<task_id>/tags", methods=["PUT"])
async def update_task_tags(task_id):
    tm = _task_manager
    if tm is None:
        return jsonify({"success": False, "message": "TaskManager 不可用"}), 503
    ident = _current_identity()
    if not ident:
        return jsonify({"success": False, "message": "未登录"}), 401

    target = next((t for t in _iter_all_tasks() if t.get("id") == task_id), None)
    if not target:
        return jsonify({"success": False, "message": "任务未找到"}), 404
    if not ident["is_admin"] and target.get("sender_id") != ident["sender_id"]:
        return jsonify({"success": False, "message": "无权限"}), 403

    data = await request.get_json() or {}
    tags = normalize_tags(data.get("tags"))
    ok = await tm.update_task_tags(task_id, tags)
    if not ok:
        return jsonify({"success": False, "message": "任务未找到"}), 404
    return jsonify({"success": True, "message": "标签已更新", "tags": tags})


@app.route("/api/tasks/bulk_delete", methods=["POST"])
async def bulk_delete_tasks():
    """Delete tasks by explicit ids or by matching any of ``tags``."""
    ident = _current_identity()
    if not ident:
        return jsonify({"success": False, "message": "未登录"}), 401

    data = await request.get_json() or {}
    ids = data.get("task_ids") or []
    tags = normalize_tags(data.get("tags"))

    target_ids: set[str] = set()
    if isinstance(ids, list):
        for tid in ids:
            if isinstance(tid, str) and tid:
                target_ids.add(tid)

    if tags:
        if not ident["is_admin"]:
            return jsonify(
                {"success": False, "message": "仅管理员可按标签批量删除"}
            ), 403
        for task in _iter_all_tasks():
            if task_has_any_tag(task, tags):
                tid = task.get("id")
                if tid:
                    target_ids.add(tid)

    if not target_ids:
        return jsonify({"success": False, "message": "未指定要删除的任务"}), 400

    deleted = 0
    for tid in list(target_ids):
        if _delete_task_by_id(tid, ident):
            deleted += 1
    return jsonify(
        {"success": True, "deleted": deleted, "message": f"已删除 {deleted} 个任务"}
    )


# --- Tag catalogue ---


@app.route("/api/tags", methods=["GET"])
async def list_tags():
    """Return task tags and user profiles visible to current identity."""
    ident = _current_identity()
    if not ident:
        return jsonify({"success": False, "message": "未登录"}), 401

    task_tag_counts: dict[str, int] = {}
    for task in _iter_all_tasks():
        if not ident["is_admin"] and task.get("sender_id") != ident["sender_id"]:
            continue
        for tag in task.get("tags", []) or []:
            if not isinstance(tag, str) or not tag:
                continue
            task_tag_counts[tag] = task_tag_counts.get(tag, 0) + 1

    task_tags = [
        {"tag": tag, "count": count}
        for tag, count in sorted(task_tag_counts.items(), key=lambda x: (-x[1], x[0]))
    ]

    tm = _task_manager
    user_tag_counts: dict[str, int] = {}
    users = []
    if tm is not None:
        profile_map = tm.get_all_user_tags()
        if ident["is_admin"]:
            for sender_id, entry in profile_map.items():
                users.append(
                    {
                        "sender_id": sender_id,
                        "umo": entry.get("umo", ""),
                        "tags": list(entry.get("tags", [])),
                    }
                )
                for tag in entry.get("tags", []):
                    user_tag_counts[tag] = user_tag_counts.get(tag, 0) + 1
            users.sort(key=lambda x: x["sender_id"])
        else:
            entry = profile_map.get(ident["sender_id"], {"umo": "", "tags": []})
            users.append(
                {
                    "sender_id": ident["sender_id"],
                    "umo": entry.get("umo", ""),
                    "tags": list(entry.get("tags", [])),
                }
            )

    user_tags = [
        {"tag": tag, "count": count}
        for tag, count in sorted(user_tag_counts.items(), key=lambda x: (-x[1], x[0]))
    ]

    return jsonify(
        {
            "task_tags": task_tags,
            "user_tags": user_tags,
            "users": users,
        }
    )


# --- User profile API ---


@app.route("/api/users", methods=["GET"])
async def list_users():
    tm = _task_manager
    if tm is None:
        return jsonify({"users": []})
    ident = _current_identity()
    if not ident:
        return jsonify({"success": False, "message": "未登录"}), 401

    profile_map = tm.get_all_user_tags()
    if ident["is_admin"]:
        users = [
            {
                "sender_id": sid,
                "umo": entry.get("umo", ""),
                "tags": list(entry.get("tags", [])),
            }
            for sid, entry in profile_map.items()
        ]
        users.sort(key=lambda x: x["sender_id"])
    else:
        entry = profile_map.get(ident["sender_id"], {"umo": "", "tags": []})
        users = [
            {
                "sender_id": ident["sender_id"],
                "umo": entry.get("umo", ""),
                "tags": list(entry.get("tags", [])),
            }
        ]
    return jsonify({"users": users})


@app.route("/api/users", methods=["POST"])
async def upsert_user():
    tm = _task_manager
    if tm is None:
        return jsonify({"success": False, "message": "TaskManager 不可用"}), 503
    ident = _current_identity()
    if not ident:
        return jsonify({"success": False, "message": "未登录"}), 401

    data = await request.get_json() or {}
    sender_id = (data.get("sender_id") or "").strip()
    if not sender_id:
        return jsonify({"success": False, "message": "sender_id 不能为空"}), 400

    if not ident["is_admin"] and sender_id != ident["sender_id"]:
        return jsonify({"success": False, "message": "无权限"}), 403

    umo = data.get("umo")
    tags = data.get("tags")

    if not ident["is_admin"]:
        umo = None

    try:
        profile = tm.set_user_profile(
            sender_id=sender_id,
            umo=(umo.strip() if isinstance(umo, str) else None),
            tags=normalize_tags(tags) if tags is not None else None,
        )
    except Exception as e:
        return jsonify({"success": False, "message": f"保存失败: {e}"}), 400
    return jsonify({"success": True, "user": profile})


@app.route("/api/users/<sender_id>", methods=["DELETE"])
async def delete_user(sender_id):
    tm = _task_manager
    if tm is None:
        return jsonify({"success": False, "message": "TaskManager 不可用"}), 503
    ident = _current_identity()
    if not ident:
        return jsonify({"success": False, "message": "未登录"}), 401
    if not ident["is_admin"]:
        return jsonify({"success": False, "message": "仅管理员可删除用户"}), 403
    if tm.delete_user_profile(sender_id):
        return jsonify({"success": True, "message": "用户已删除"})
    return jsonify({"success": False, "message": "用户未找到"}), 404


# --- Server lifecycle ---


def run_server(config, task_manager=None):
    """Entry point for the worker thread."""
    asyncio.run(start_server(config, task_manager))


def stop_server():
    """请求异步服务器关闭，可从任意线程调用。

    asyncio.Event.set() 是官方文档保证线程安全的。
    """
    global _shutdown_event
    if _shutdown_event:
        _shutdown_event.set()
        logger.info("WebUI server shutdown requested")


async def start_server(config=None, task_manager=None):
    global _shutdown_event, _task_manager
    config = config or {}
    port = config.get("webui_port", 5001)
    if task_manager is not None:
        _task_manager = task_manager
    app.secret_key = secrets.token_urlsafe(32)

    hypercorn_config = Config()
    hypercorn_config.bind = [f"0.0.0.0:{port}"]
    hypercorn_config.graceful_timeout = 5

    _shutdown_event = asyncio.Event()
    try:
        await hypercorn.asyncio.serve(
            app, hypercorn_config, shutdown_trigger=_shutdown_event.wait
        )
    finally:
        _shutdown_event = None
        logger.info("WebUI server stopped")
