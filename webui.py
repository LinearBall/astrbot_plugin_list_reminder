import asyncio
import json
import os
import secrets
from datetime import datetime
from pathlib import Path

import hypercorn.asyncio
from hypercorn.config import Config
from quart import (
    Quart,
    jsonify,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)

from astrbot.api import logger

# 配置
PLUGIN_DIR = Path(__file__).parent.absolute()
DATA_DIR = PLUGIN_DIR / "data"
USERS_DIR = DATA_DIR / "users"
GROUPS_DIR = DATA_DIR / "groups"

# 确保目录存在
USERS_DIR.mkdir(parents=True, exist_ok=True)
GROUPS_DIR.mkdir(parents=True, exist_ok=True)


class ServerState:
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance.ready = asyncio.Event()
            cls._instance.port = 5001
        return cls._instance


app = Quart(__name__)

SERVER_LOGIN_KEY = None
_current_server = None
_task_manager_ref = None

# 简单的HTML模板
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>登录 - 任务管理系统</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 300px; }
        h1 { text-align: center; color: #333; margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; }
        input[type="password"] { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; font-size: 14px; }
        button { width: 100%; padding: 12px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }
        button:hover { background: #0056b3; }
        .error { color: #dc3545; text-align: center; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>🔐 任务管理系统</h1>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <div class="form-group">
                <input type="password" name="key" placeholder="请输入登录密钥" required>
            </div>
            <button type="submit">登录</button>
        </form>
    </div>
</body>
</html>
"""

INDEX_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>任务管理系统</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; }
        .header { background: #007bff; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .header h1 { margin: 0; }
        .header p { margin: 10px 0 0 0; opacity: 0.9; }
        .content { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .card h2 { margin-top: 0; color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; color: #555; font-weight: 500; }
        input, textarea, select { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
        textarea { resize: vertical; min-height: 80px; }
        button { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
        button:hover { background: #0056b3; }
        button.danger { background: #dc3545; }
        button.danger:hover { background: #c82333; }
        .task-list { list-style: none; padding: 0; margin: 0; }
        .task-item { padding: 15px; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 10px; }
        .task-item.completed { background: #f8f9fa; opacity: 0.7; }
        .task-item.completed .task-content { text-decoration: line-through; }
        .task-time { color: #666; font-size: 12px; margin-bottom: 5px; }
        .task-content { font-size: 16px; color: #333; margin-bottom: 10px; }
        .task-meta { display: flex; justify-content: space-between; align-items: center; }
        .task-type { display: inline-block; padding: 2px 8px; background: #e9ecef; border-radius: 3px; font-size: 12px; color: #495057; }
        .task-actions button { padding: 5px 10px; font-size: 12px; }
        .tabs { display: flex; margin-bottom: 15px; border-bottom: 2px solid #e9ecef; }
        .tab { padding: 10px 20px; cursor: pointer; border-bottom: 3px solid transparent; }
        .tab.active { border-bottom-color: #007bff; color: #007bff; font-weight: 500; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .logout { text-align: right; margin-top: 20px; }
        .logout button { background: #6c757d; }
        .logout button:hover { background: #5a6268; }
        @media (max-width: 768px) {
            .content { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📝 任务管理系统</h1>
            <p>创建和管理定时任务</p>
        </div>

        <div class="content">
            <div class="card">
                <h2>创建新任务</h2>
                <form id="createTaskForm">
                    <div class="form-group">
                        <label>任务类型</label>
                        <select id="taskType">
                            <option value="user">用户任务</option>
                            <option value="group">群组任务</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>目标ID</label>
                        <input type="text" id="targetId" placeholder="用户ID或群组ID" required>
                    </div>
                    <div class="form-group">
                        <label>提醒时间</label>
                        <input type="datetime-local" id="taskTime" required>
                    </div>
                    <div class="form-group">
                        <label>任务内容</label>
                        <textarea id="taskContent" placeholder="输入要提醒的内容" required></textarea>
                    </div>
                    <button type="submit">创建任务</button>
                </form>
            </div>

            <div class="card">
                <h2>任务列表</h2>
                <div class="tabs">
                    <div class="tab active" data-tab="user">用户任务</div>
                    <div class="tab" data-tab="group">群组任务</div>
                </div>
                <div id="userTasks" class="tab-content active">
                    <ul id="userTaskList" class="task-list"></ul>
                </div>
                <div id="groupTasks" class="tab-content">
                    <ul id="groupTaskList" class="task-list"></ul>
                </div>
            </div>
        </div>

        <div class="logout">
            <button onclick="logout()">退出登录</button>
        </div>
    </div>

    <script>
        // 标签切换
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(tab.dataset.tab + 'Tasks').classList.add('active');
            });
        });

        // 创建任务
        document.getElementById('createTaskForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const taskType = document.getElementById('taskType').value;
            const targetId = document.getElementById('targetId').value;
            const taskTime = document.getElementById('taskTime').value;
            const taskContent = document.getElementById('taskContent').value;

            try {
                const response = await fetch('/api/tasks', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        type: taskType,
                        target_id: targetId,
                        time: taskTime,
                        content: taskContent
                    })
                });
                const result = await response.json();
                if (result.success) {
                    alert('✅ 任务创建成功！');
                    document.getElementById('createTaskForm').reset();
                    loadTasks();
                } else {
                    alert('❌ 创建失败: ' + result.message);
                }
            } catch (error) {
                alert('网络错误: ' + error.message);
            }
        });

        // 加载任务
        async function loadTasks() {
            try {
                const response = await fetch('/api/tasks');
                const data = await response.json();

                const userTasksHtml = data.user_tasks.map(task => `
                    <li class="task-item ${task.completed ? 'completed' : ''}">
                        <div class="task-time">📅 ${task.time}</div>
                        <div class="task-content">${task.content}</div>
                        <div class="task-meta">
                            <span class="task-type">${task.target_id}</span>
                            <div class="task-actions">
                                ${!task.completed ? `<button class="danger" onclick="deleteTask('${task.id}')">删除</button>` : ''}
                            </div>
                        </div>
                    </li>
                `).join('');

                const groupTasksHtml = data.group_tasks.map(task => `
                    <li class="task-item ${task.completed ? 'completed' : ''}">
                        <div class="task-time">📅 ${task.time}</div>
                        <div class="task-content">${task.content}</div>
                        <div class="task-meta">
                            <span class="task-type">👥 ${task.target_id}</span>
                            <div class="task-actions">
                                ${!task.completed ? `<button class="danger" onclick="deleteTask('${task.id}')">删除</button>` : ''}
                            </div>
                        </div>
                    </li>
                `).join('');

                document.getElementById('userTaskList').innerHTML = userTasksHtml || '<li style="padding:20px;color:#666;text-align:center;">暂无用户任务</li>';
                document.getElementById('groupTaskList').innerHTML = groupTasksHtml || '<li style="padding:20px;color:#666;text-align:center;">暂无群组任务</li>';
            } catch (error) {
                console.error('加载任务失败:', error);
            }
        }

        // 删除任务
        async function deleteTask(taskId) {
            if (!confirm('确定要删除这个任务吗？')) return;
            try {
                const response = await fetch(`/api/tasks/${taskId}`, {method: 'DELETE'});
                const result = await response.json();
                if (result.success) {
                    alert('🗑️ 任务已删除');
                    loadTasks();
                } else {
                    alert('删除失败: ' + result.message);
                }
            } catch (error) {
                alert('网络错误: ' + error.message);
            }
        }

        // 退出登录
        function logout() {
            fetch('/logout', {method: 'POST'}).then(() => {
                window.location.href = '/login';
            });
        }

        // 页面加载时获取任务
        document.addEventListener('DOMContentLoaded', loadTasks);
    </script>
</body>
</html>
"""


@app.route("/health", methods=["GET"])
async def health_check():
    """健康检查接口"""
    return jsonify({"status": "running", "version": "1.0"})


@app.before_request
async def require_login():
    allowed_endpoints = ["login", "static", "health_check"]
    if request.endpoint not in allowed_endpoints and not session.get("authenticated"):
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
async def login():
    if session.get("authenticated"):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        form_data = await request.form
        key = form_data.get("key")
        if key == SERVER_LOGIN_KEY:
            session["authenticated"] = True
            return redirect(url_for("index"))
        else:
            error = "秘钥错误，请重试。"
    return await render_template_string(LOGIN_TEMPLATE, error=error)


@app.route("/logout", methods=["POST"])
async def logout():
    session.pop("authenticated", None)
    return redirect(url_for("login"))


@app.route("/")
async def index():
    if not session.get("authenticated"):
        return redirect(url_for("login"))
    return await render_template_string(INDEX_TEMPLATE)


@app.route("/api/tasks", methods=["GET"])
async def list_tasks():
    """获取所有任务"""
    user_tasks = []
    group_tasks = []

    # 读取用户任务
    for user_file in USERS_DIR.glob("user_*.json"):
        try:
            with open(user_file, encoding="utf-8") as f:
                data = json.load(f)
                user_id = user_file.stem.replace("user_", "")
                for task in data.get("tasks", []):
                    task["target_id"] = user_id
                    user_tasks.append(task)
        except Exception:
            pass

    # 读取群组任务
    for group_file in GROUPS_DIR.glob("group_*.json"):
        try:
            with open(group_file, encoding="utf-8") as f:
                data = json.load(f)
                group_id = group_file.stem.replace("group_", "")
                for task in data.get("tasks", []):
                    task["target_id"] = group_id
                    group_tasks.append(task)
        except Exception:
            pass

    # 按时间排序
    user_tasks.sort(key=lambda x: x["time"])
    group_tasks.sort(key=lambda x: x["time"])

    return jsonify({"user_tasks": user_tasks, "group_tasks": group_tasks})


@app.route("/api/tasks", methods=["POST"])
async def create_task():
    """创建任务"""
    try:
        data = await request.get_json()
        task_type = data.get("type")
        target_id = data.get("target_id")
        task_time = data.get("time")
        content = data.get("content")

        if not task_type or not target_id or not task_time or not content:
            return jsonify({"success": False, "message": "缺少必要参数"})

        # 转换时间格式 (datetime-local 格式: 2024-01-01T15:00)
        try:
            # 处理 datetime-local 格式，添加秒
            if "T" in task_time and len(task_time.split(":")) == 2:
                task_time += ":00"
            dt = datetime.fromisoformat(task_time)
            task_time_iso = dt.isoformat()
        except Exception as e:
            logger.error(f"时间格式转换失败: {e}")
            return jsonify({"success": False, "message": "时间格式错误"})

        # 保存任务
        is_group = task_type == "group"
        if is_group:
            file = GROUPS_DIR / f"group_{target_id}.json"
        else:
            file = USERS_DIR / f"user_{target_id}.json"

        task_data = {"tasks": []}
        if file.exists():
            with open(file, encoding="utf-8") as f:
                task_data = json.load(f)

        task = {
            "id": f"{target_id}_{int(datetime.now().timestamp())}",
            "target_id": target_id,
            "time": task_time_iso,
            "content": content,
            "creator": "webui",
            "umo": "",
            "created_at": datetime.now().isoformat(),
            "completed": False,
            "is_group": is_group
        }

        task_data["tasks"].append(task)

        with open(file, "w", encoding="utf-8") as f:
            json.dump(task_data, f, ensure_ascii=False)

        # 任务已保存到文件，重启AstrBot后会自动加载定时器
        return jsonify({"success": True, "message": "任务创建成功，重启AstrBot后生效"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
async def delete_task(task_id):
    """删除任务"""
    try:
        # 查找并删除任务
        for user_file in USERS_DIR.glob("user_*.json"):
            if await _remove_task_from_file(user_file, task_id):
                return jsonify({"success": True, "message": "任务删除成功"})

        for group_file in GROUPS_DIR.glob("group_*.json"):
            if await _remove_task_from_file(group_file, task_id):
                return jsonify({"success": True, "message": "任务删除成功"})

        return jsonify({"success": False, "message": "任务未找到"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


async def _remove_task_from_file(file_path: Path, task_id: str) -> bool:
    """从文件中移除任务"""
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        original_len = len(data.get("tasks", []))
        data["tasks"] = [t for t in data.get("tasks", []) if t["id"] != task_id]

        if len(data["tasks"]) < original_len:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            return True
        return False
    except Exception:
        return False


# 提供同步的入口
def run_server(config, task_manager=None):
    asyncio.run(start_server(config, task_manager))


async def start_server(config=None, task_manager=None):
    """启动服务器"""
    global SERVER_LOGIN_KEY, _current_server, _task_manager_ref

    state = ServerState()
    state.ready.clear()

    port = config.get("webui_port", 5001)
    SERVER_LOGIN_KEY = config.get("server_key")
    if not SERVER_LOGIN_KEY:
        SERVER_LOGIN_KEY = secrets.token_urlsafe(16)
        logger.info(f"自动生成的WebUI登录密钥: {SERVER_LOGIN_KEY}")

    _task_manager_ref = task_manager

    # 配置应用
    app.secret_key = os.urandom(16)
    app.config["PLUGIN_CONFIG"] = {
        "webui_port": port,
    }

    @app.before_serving
    async def notify_ready():
        state.ready.set()

    # 启动服务器
    hypercorn_config = Config()
    hypercorn_config.bind = [f"0.0.0.0:{port}"]
    hypercorn_config.graceful_timeout = 5

    _current_server = await hypercorn.asyncio.serve(
        app,
        hypercorn_config,
    )
    return SERVER_LOGIN_KEY
