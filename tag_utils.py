# 标签工具模块（主插件与 WebUI 共享）
#
# 标签规则：
# - 每个标签是非空且去除首尾空白的字符串，保留原始大小写
# - 过滤时不区分大小写匹配，但存储时保留用户输入的原始大小写
# - task_tags 存储在单条任务记录上（task['tags']）
# - user_tags 存储在共享 JSON 文件中，以 sender_id 为键，附带最近一次的 umo

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def normalize_tags(raw) -> list[str]:
    # 对标签列表进行去重、去空、去除首尾空白
    # 支持传入列表/元组，或逗号、顿号、分号分隔的字符串
    # 去重时不区分大小写，保留首次出现的形式
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = []
        for chunk in (
            raw.replace("，", ",").replace("、", ",").replace(";", ",").split(",")
        ):
            parts.append(chunk)
    else:
        try:
            parts = list(raw)
        except TypeError:
            return []

    seen = set()
    result = []
    for item in parts:
        if not isinstance(item, str):
            continue
        tag = item.strip()
        if not tag:
            continue
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(tag)
    return result


def task_has_any_tag(task: dict, wanted: list[str]) -> bool:
    # 判断任务是否包含任一目标标签（不区分大小写）
    if not wanted:
        return False
    task_tags = {t.casefold() for t in task.get("tags", []) if isinstance(t, str)}
    return any(w.casefold() in task_tags for w in wanted if w)


def load_user_tags(path: Path) -> dict:
    # 加载 user_tags 映射，返回 {sender_id: {'umo': str, 'tags': [str]}}
    # 文件不存在或格式错误时返回空字典
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}

    result = {}
    for sender_id, entry in data.items():
        if not isinstance(sender_id, str) or not sender_id:
            continue
        if not isinstance(entry, dict):
            continue
        result[sender_id] = {
            "umo": (entry.get("umo") or "").strip(),
            "tags": normalize_tags(entry.get("tags")),
        }
    return result


def save_user_tags(path: Path, data: dict) -> None:
    # 原子化写入 user_tags 映射文件（先写临时文件再替换，避免数据损坏）
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".user_tags_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def find_users_by_tag(user_tags: dict, tag: str) -> list[dict]:
    # 根据 user_tag 查找匹配的用户，返回 [{sender_id, umo, tags}] 列表
    # 匹配时不区分大小写
    if not tag:
        return []
    needle = tag.casefold()
    out = []
    for sender_id, entry in user_tags.items():
        tags = entry.get("tags", [])
        if any(isinstance(t, str) and t.casefold() == needle for t in tags):
            out.append(
                {
                    "sender_id": sender_id,
                    "umo": entry.get("umo", ""),
                    "tags": list(tags),
                }
            )
    return out
