import asyncio
import secrets
from pathlib import Path
from typing import Dict, List

import hypercorn.asyncio
import pydantic
from astrbot.api import logger
from hypercorn.config import Config
from quart import Quart, jsonify, request, send_from_directory, session

from .db_utils import EditTodoPayload, Todo
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
    def __init__(self, tm: TodoManager, admin_sender_ids: set[str] | None = None) -> None:
        self.tm = tm
        self.admin_sender_ids = set(admin_sender_ids or [])
        self.app = Quart(__name__)
        self.login_keys: Dict[str, str] = dict()
        self.sender_id_2_umo: Dict[str, str] = dict()
        self._shutdown_event: asyncio.Event | None = None

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

    def _request_auth_key(self) -> str:
        """读取请求头中的登录密钥（方案A：每个标签页携带自己的 key）。"""
        return (request.headers.get("X-Auth-Key") or "").strip()

    def current_request_sender_id(self) -> str | None:
        """优先用请求头 key 识别身份，其次回退到 session 登录态。

        Returns:
            当前请求对应的 sender_id；未登录返回 None。
        """
        key = self._request_auth_key()
        if key and key in self.login_keys:
            return self.login_keys[key]
        return self.current_session_sender_id()

    def is_admin_user(self, sender_id: str) -> bool:
        """判断指定用户在 userDB 中是否为管理员。

        Args:
            sender_id: 用户 sender_id。

        Returns:
            是否为管理员。
        """
        user = self.tm.user_db.get_user(sender_id) if self.tm else None
        return bool(user and user.is_admin)

    def current_request_is_admin(self) -> bool:
        """当前请求的用户在 userDB 中是否为管理员。"""
        sender_id = self.current_request_sender_id()
        return bool(sender_id) and self.is_admin_user(sender_id)

    def _owner_umo(self, owner: str, current_sender: str) -> str:
        """解析任务所有者的推送会话 umo。

        Args:
            owner: 任务所有者 sender_id。
            current_sender: 当前登录用户 sender_id。

        Returns:
            推送使用的 umo 字符串；无法确定时返回空串。
        """
        if owner and owner == current_sender:
            umo = self.sender_id_2_umo.get(owner, "")
            if umo:
                return umo
        user = self.tm.user_db.get_user(owner) if self.tm else None
        if user and (user.umo or "").strip():
            return user.umo
        return self.sender_id_2_umo.get(owner, "")

    # --- Auth ---
    def init_before_request(self):
        @self.app.before_request
        async def check_if_logged_in():
            # 1. 允许放行已有登录会话的用户
            if self.current_request_sender_id():
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
            sender_id = self.current_request_sender_id()
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
            sender_id = self.current_request_sender_id()
            if not sender_id:
                return api_error(401, "未登录")
            return api_success(sender_id=sender_id, is_admin=self.is_admin_user(sender_id))

        @self.app.route("/api/todos", methods=["GET"])
        async def list_todos():
            """
            获取当前登陆用户的所有任务。
            任务按到期时间排序，最早到期在前。
            """
            sender_id = self.current_request_sender_id()
            if not sender_id:
                return api_error(401, "未登录")
            if self.current_request_is_admin():
                todos: List[Todo] = self.tm.get_all_todos()
            else:
                todos = self.tm.get_todos_by_creator(sender_id)
            todos.sort(key=lambda t: t.due_time)
            return api_success(todos=[t.model_dump() for t in todos])

        @self.app.route("/api/todos", methods=["POST"])
        async def create_todo():
            sender_id = self.current_request_sender_id()
            if not sender_id:
                return api_error(401, "未登录")

            try:
                data = await request.get_json(silent=True) or {}
            except pydantic.ValidationError:
                return api_error(400, "内容、时间、umo 不能为空")
            content = (data.get("content") or "").strip()
            due_time = data.get("due_time")
            completed = data.get("completed", False)
            if not content or not due_time:
                return api_error(400, "内容、到期时间不能为空")

            owners = data.get("owners") or [sender_id]
            if isinstance(owners, str):
                owners = [owners]
            tags = data.get("tags") or []
            created: List[int] = []
            for owner in owners:
                owner = str(owner).strip()
                if not owner:
                    continue
                umo = self._owner_umo(owner, sender_id)
                if not umo:
                    continue
                todo_id = self.tm.create_todo(
                    creator=owner,
                    umo=umo,
                    content=content,
                    due_time=due_time,
                    completed=completed,
                    tags=list(tags),
                )
                if todo_id != -1:
                    created.append(todo_id)
            if not created:
                logger.error("WebUI 创建任务失败：任务到期时间太早或缺少会话信息")
                return api_error(500, "创建失败：任务到期时间太早或缺少会话信息")
            return api_success(message=f"已创建 {len(created)} 个任务", todo_ids=created)

        @self.app.route("/api/todos/<int:todo_id>", methods=["PUT"])
        async def update_todo(todo_id):
            sender_id = self.current_request_sender_id()
            if not sender_id:
                return api_error(401, "未登录")

            data: EditTodoPayload = await request.get_json(silent=True)
            content = data["content"]
            due_time = data["due_time"]
            completed = data["completed"]
            if not content or not due_time:
                return api_error(400, "内容、到期时间不能为空")

            todo = self.tm.db.get_todo_by_id(todo_id)
            if not todo or (todo.creator != sender_id and not self.current_request_is_admin()):
                return api_error(404, "任务未找到或无权限")
            updated_todo_id = self.tm.update_todo(todo_id, content, due_time, completed)
            if updated_todo_id == -1:
                return api_error(500, "更新失败：任务不存在")

            return api_success(message="任务已更新", todo_id=updated_todo_id)

        @self.app.route("/api/todos/<int:todo_id>", methods=["DELETE"])
        async def delete_todo(todo_id):
            sender_id = self.current_request_sender_id()
            if not sender_id:
                return api_error(401, "未登录")

            todo = self.tm.db.get_todo_by_id(todo_id)
            if not todo or (todo.creator != sender_id and not self.current_request_is_admin()):
                return api_error(404, "任务未找到或无权限")

            self.tm.db.delete_todo(todo_id)
            timer = self.tm.active_timers.pop(todo_id, None)
            if timer and not timer.done():
                timer.cancel()
            return api_success(message="任务已删除")

        @self.app.route("/api/admin/toggle", methods=["POST"])
        async def toggle_admin():
            sender_id = self.current_request_sender_id()
            if not sender_id:
                return api_error(401, "未登录")
            user = self.tm.user_db.get_user(sender_id)
            current_admin = bool(user and user.is_admin)
            umo = (user.umo if user else "") or self.sender_id_2_umo.get(sender_id, "")
            if current_admin:
                self.tm.user_db.add_or_update_user(sender_id, umo, is_admin=False)
                return api_success(is_admin=False, message="已关闭管理员权限")
            if sender_id in self.admin_sender_ids:
                self.tm.user_db.add_or_update_user(sender_id, umo, is_admin=True)
                return api_success(is_admin=True, message="已开启管理员权限")
            return api_error(403, "您不是管理员，无法开启管理员权限")

        @self.app.route("/api/tags", methods=["GET"])
        async def list_tag_catalogue():
            sender_id = self.current_request_sender_id()
            if not sender_id:
                return api_error(401, "未登录")
            is_admin = self.is_admin_user(sender_id)
            if is_admin:
                users = [
                    {
                        "sender_id": u.sender_id,
                        "umo": u.umo,
                        "is_admin": u.is_admin,
                        "nickname": u.nickname or u.sender_id,
                        "tags": self.tm.tag_db.get_user_tags(u.sender_id),
                    }
                    for u in self.tm.user_db.list_users()
                ]
            else:
                own = self.tm.user_db.get_user(sender_id)
                users = [
                    {
                        "sender_id": sender_id,
                        "umo": (own.umo if own else ""),
                        "is_admin": bool(own and own.is_admin),
                        "nickname": (own.nickname or sender_id) if own else sender_id,
                        "tags": self.tm.tag_db.get_user_tags(sender_id),
                    }
                ]
            tag_senders: Dict[str, List[str]] = {}
            for u in users:
                for tag in u["tags"]:
                    tag_senders.setdefault(tag, []).append(u["sender_id"])
            return api_success(is_admin=is_admin, users=users, tag_senders=tag_senders)

        @self.app.route("/api/tags", methods=["POST"])
        async def add_user_tag():
            sender_id = self.current_request_sender_id()
            if not sender_id:
                return api_error(401, "未登录")
            body = await request.get_json(silent=True) or {}
            tag = (body.get("tag") or "").strip()
            if not tag:
                return api_error(400, "标签不能为空")
            target = (body.get("sender_id") or sender_id).strip()
            if target != sender_id and not self.is_admin_user(sender_id):
                return api_error(403, "无权限")
            user = self.tm.user_db.get_user(target)
            umo = (user.umo if user else "") or self.sender_id_2_umo.get(target, "")
            self.tm.user_db.add_or_update_user(target, umo, bool(user and user.is_admin))
            self.tm.tag_db.attach_tag_to_user(target, tag)
            return api_success(message="标签已添加", tags=self.tm.tag_db.get_user_tags(target))

        @self.app.route("/api/tags", methods=["DELETE"])
        async def remove_user_tag():
            sender_id = self.current_request_sender_id()
            if not sender_id:
                return api_error(401, "未登录")
            body = await request.get_json(silent=True) or {}
            tag = (body.get("tag") or "").strip()
            if not tag:
                return api_error(400, "标签不能为空")
            target = (body.get("sender_id") or sender_id).strip()
            if target != sender_id and not self.is_admin_user(sender_id):
                return api_error(403, "无权限")
            removed = self.tm.tag_db.remove_tag_from_user(target, tag)
            return api_success(removed=bool(removed), tags=self.tm.tag_db.get_user_tags(target))

        @self.app.route("/api/users/nickname", methods=["POST"])
        async def update_own_nickname():
            sender_id = self.current_request_sender_id()
            if not sender_id:
                return api_error(401, "未登录")
            body = await request.get_json(silent=True) or {}
            nickname = (body.get("nickname") or "").strip()
            if not nickname:
                return api_error(400, "昵称不能为空")
            self.tm.user_db.update_nickname(sender_id, nickname)
            return api_success(message="昵称已更新", nickname=nickname)

        @self.app.route("/api/users/<sender_id>", methods=["GET"])
        async def get_user_detail(sender_id):
            """查询某用户的完整信息（userDB 所有字段 + 关联标签）。

            普通用户只能查看自己；管理员可查看任意用户。
            """
            current = self.current_request_sender_id()
            if not current:
                return api_error(401, "未登录")
            if sender_id != current and not self.current_request_is_admin():
                return api_error(403, "无权限")
            user = self.tm.user_db.get_user(sender_id)
            if not user:
                return api_error(404, "用户不存在")
            return api_success(
                sender_id=user.sender_id,
                umo=user.umo,
                is_admin=user.is_admin,
                nickname=user.nickname or user.sender_id,
                tags=self.tm.tag_db.get_user_tags(sender_id),
            )

    # --- Server lifecycle ---
    def request_shutdown(self):
        """
        触发 hypercorn 的 shutdown_trigger，等待存量连接处理完后退出。
        """
        if self._shutdown_event:
            self._shutdown_event.set()

    def clear_sessions(self):
        """清空已下发的登录密钥与会话绑定。"""
        self.login_keys.clear()
        self.sender_id_2_umo.clear()

    async def start_server(self, port: int = 5001):
        self.app.secret_key = secrets.token_urlsafe(32)  # 听说是用于session加密的密钥

        hypercorn_config = Config()
        hypercorn_config.bind = [f"0.0.0.0:{port}"]
        hypercorn_config.graceful_timeout = 5

        # Provide a shutdown trigger so hypercorn skips its signal-handler
        # setup, which crashes in a non-main thread on Windows.
        self._shutdown_event = asyncio.Event()
        try:
            await hypercorn.asyncio.serve(
                self.app, hypercorn_config, shutdown_trigger=self._shutdown_event.wait
            )
        except asyncio.CancelledError:
            logger.info("WebUI server task 被取消")
            raise
        except Exception:
            logger.exception("WebUI server 运行异常")
        finally:
            self._shutdown_event = None
