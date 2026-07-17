from pathlib import Path
from astrbot.core.utils.astrbot_path import (
    get_astrbot_plugin_data_path,  # 新版插件目录
)

# 配置
PLUGIN_DIR = Path(__file__).parent.absolute()
PLUGIN_NAME = "list_reminder"
PLUGIN_DATA_ROOT = (Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME).resolve()
USERS_DIR = PLUGIN_DATA_ROOT / "users"
GROUPS_DIR = PLUGIN_DATA_ROOT / "groups"

# 确保目录存在
USERS_DIR.mkdir(parents=True, exist_ok=True)
GROUPS_DIR.mkdir(parents=True, exist_ok=True)