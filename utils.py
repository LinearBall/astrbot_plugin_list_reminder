# 工具函数模块

import json
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> None:
    # 确保目录存在，不存在则创建
    path.mkdir(parents=True, exist_ok=True)


def save_json(data: Any, file_path: Path) -> bool:
    # 将 JSON 数据保存到文件，成功返回 True
    try:
        ensure_dir(file_path.parent)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存 JSON 文件失败: {e}")
        return False


def load_json(file_path: Path) -> Any | None:
    # 从文件加载 JSON 数据，文件不存在或加载失败返回 None
    if not file_path.exists():
        return None

    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"加载 JSON 文件失败: {e}")
        return None


def get_task_stats(tasks: list[dict[str, Any]]) -> dict[str, int]:
    # 统计任务列表的各项数量（总数、待完成、已完成、各优先级数量）
    stats = {
        "total": len(tasks),
        "pending": 0,
        "completed": 0,
        "high_priority": 0,
        "medium_priority": 0,
        "low_priority": 0,
    }

    for task in tasks:
        if task.get("completed", False):
            stats["completed"] += 1
        else:
            stats["pending"] += 1

        priority = task.get("priority", "medium")
        stats[f"{priority}_priority"] += 1

    return stats
