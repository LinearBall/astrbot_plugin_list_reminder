from pathlib import Path

from astrbot.core.utils.astrbot_path import (
    get_astrbot_plugin_data_path,  # 新版插件目录
)

# 插件名称
PLUGIN_NAME = "list_reminder"

# 插件根目录（当前文件所在目录）
PLUGIN_DIR = Path(__file__).parent.absolute()

# 插件数据根目录（AstrBot 统一管理的插件数据路径）
PLUGIN_DATA_ROOT = (Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME).resolve()

# 用户任务文件存放目录
USERS_DIR = PLUGIN_DATA_ROOT / "users"

# 用户标签映射文件
USER_TAGS_FILE = PLUGIN_DATA_ROOT / "user_tags.json"

# 确保数据目录存在
USERS_DIR.mkdir(parents=True, exist_ok=True)
