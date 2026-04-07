"""工具函数模块"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def ensure_dir(path: Path) -> None:
    """确保目录存在"""
    path.mkdir(parents=True, exist_ok=True)


def save_json(data: Any, file_path: Path) -> bool:
    """保存 JSON 数据到文件"""
    try:
        ensure_dir(file_path.parent)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存 JSON 文件失败: {e}")
        return False


def load_json(file_path: Path) -> Optional[Any]:
    """从文件加载 JSON 数据"""
    if not file_path.exists():
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载 JSON 文件失败: {e}")
        return None


def get_task_stats(tasks: List[Dict[str, Any]]) -> Dict[str, int]:
    """获取任务统计信息"""
    stats = {
        "total": len(tasks),
        "pending": 0,
        "completed": 0,
        "high_priority": 0,
        "medium_priority": 0,
        "low_priority": 0
    }

    for task in tasks:
        if task.get("completed", False):
            stats["completed"] += 1
        else:
            stats["pending"] += 1

        priority = task.get("priority", "medium")
        stats[f"{priority}_priority"] += 1

    return stats