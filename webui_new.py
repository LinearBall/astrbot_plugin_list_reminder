from .shared_types import RespTemplate

import asyncio

from pathlib import Path
import hypercorn.asyncio as hcasyncio
from hypercorn.config import Config as HCCOnfig
from quart import (
    Quart,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from .task_manager_new import TaskManagerNew

DIST_DIR: Path = Path(__file__).parent / "dist"
GLOBAL_TASK_MANAGER: TaskManagerNew | None = None
APP: Quart = Quart(
    __name__, static_folder=str(DIST_DIR / "assets"), static_url_path="/assets"
)
SV_KEY: str | None = ""


def set_tm(tm: TaskManagerNew):
    global GLOBAL_TASK_MANAGER
    GLOBAL_TASK_MANAGER = tm


@APP.route("/api/login", methods=["POST"])
async def api_login():
    """
    当客户端使用POST方法访问该API时，检查用户输入的密钥，并设置session["is_logged_in"]
    """
    data = await request.get_json()
    input_key = data.get("sv_key", "").strip()
    if input_key == SV_KEY:
        session["is_logged_in"] = True
        return jsonify(RespTemplate(200, message="登录成功"))
    else:
        session["is_logged_in"] = False
        return jsonify(RespTemplate(401, message="密钥错误"))


@APP.route("/api/logout", methods=["POST"])
async def api_logout():
    """
    当客户端访问该API时，设置session["is_logged_in"]为False，注销用户登录
    """
    session["is_logged_in"] = False
    return jsonify(RespTemplate(200, message="注销成功"))


@APP.route("/")
@APP.route("/<path:pp>")
async def serve_spa(pp: str):
    """
    Vue 3应用的入口
    """
    file_path = DIST_DIR / pp
    if pp and file_path.exists() and file_path.is_file():
        return await send_from_directory(DIST_DIR, pp)
    return await send_from_directory(DIST_DIR, "index.html")


async def start_server(tm: TaskManagerNew, port: int = 5001):
    """
    开启一个协程，启动WebUI服务器，允许用户访问以对任务进行增删改查操作
    """
    global GLOBAL_TASK_MANAGER, SV_KEY
    # 在启动服务器时马上设置任务管理器
    GLOBAL_TASK_MANAGER = tm
    # 配置Hypercorn服务器
    hypercorn_config = HCCOnfig()
    hypercorn_config.bind = ["0.0.0.0:{}".format(port)]
    hypercorn_config.graceful_timeout = 5
    shutdown_event = asyncio.Event()
    # 启动！
    await hcasyncio.serve(APP, hypercorn_config, shutdown_trigger=shutdown_event.wait)
