"""
模板展开结果缓存（持久化）

将跨页模板展开结果保存到磁盘，避免重复 API 请求。

存储位置：~/.cache/mdifier/templates.json
有效期：7 天（wiki 内容会更新）
"""

import json
import os
import time
from datetime import UTC
from pathlib import Path

from minecraft_wiki_mdifier.exceptions import CacheError

CACHE_DIR = Path(os.getenv("MDIFFER_CACHE_DIR", Path.home() / ".cache" / "mdifier"))
CACHE_FILE = CACHE_DIR / "templates.json"

# 缓存有效期（7 天，wiki 内容会更新）
CACHE_TTL = 7 * 24 * 3600

# 模块级单例：跨 lang 复用同一份持久化缓存，只在首次使用时懒加载
_SHARED_PERSISTENT_CACHE: dict | None = None


def get_or_load_persistent_cache() -> dict:
    """懒加载持久化缓存，全局只读一次磁盘。"""
    global _SHARED_PERSISTENT_CACHE
    if _SHARED_PERSISTENT_CACHE is None:
        _SHARED_PERSISTENT_CACHE = load_cache()
    return _SHARED_PERSISTENT_CACHE


def reset_persistent_cache() -> None:
    """重置单例（测试用）。"""
    global _SHARED_PERSISTENT_CACHE
    _SHARED_PERSISTENT_CACHE = None


def load_cache() -> dict:
    """从磁盘加载缓存；过期或不存在则返回空 dict

    Returns:
        {cache_key: {name, class, text, html, format, table, ts}}
    """
    if not CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        now = time.time()
        # 过滤过期项（无 ts 的条目视为当前，不过期）
        return {k: v for k, v in data.items() if now - v.get("ts", now) < CACHE_TTL}
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache: dict) -> None:
    """保存缓存到磁盘（添加时间戳用于 TTL）

    Args:
        cache: 模板缓存 dict
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    enriched = {k: {**v, "ts": time.time()} for k, v in cache.items()}
    try:
        CACHE_FILE.write_text(json.dumps(enriched, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        raise CacheError(f"缓存写入失败: {e}") from e


def clear_cache() -> bool:
    """清空缓存（删除磁盘文件）

    Returns:
        True 如果文件存在并被删除；False 如果缓存不存在
    """
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
        return True
    return False


def cache_info() -> dict:
    """返回缓存统计信息

    Returns:
        {
            "path": 缓存文件路径,
            "exists": 是否存在,
            "size_bytes": 文件大小（如果存在）,
            "size_mb": 文件大小 MB,
            "entries": 总条目数,
            "fresh_entries": 未过期条目数,
            "expired_entries": 已过期条目数,
            "oldest_ts": 最早时间戳（ISO 格式）,
            "newest_ts": 最新时间戳（ISO 格式）,
        }
    """
    from datetime import datetime

    info = {
        "path": str(CACHE_FILE),
        "exists": CACHE_FILE.exists(),
        "size_bytes": 0,
        "size_mb": 0.0,
        "entries": 0,
        "fresh_entries": 0,
        "expired_entries": 0,
        "oldest_ts": None,
        "newest_ts": None,
    }
    if not CACHE_FILE.exists():
        return info

    info["size_bytes"] = CACHE_FILE.stat().st_size
    info["size_mb"] = round(info["size_bytes"] / 1024 / 1024, 2)

    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        info["entries"] = len(data)
        now = time.time()
        ts_list = [v.get("ts", 0) for v in data.values() if "ts" in v]
        for v in data.values():
            ts = v.get("ts", 0)
            if now - ts < CACHE_TTL:
                info["fresh_entries"] += 1
            else:
                info["expired_entries"] += 1
        if ts_list:
            info["oldest_ts"] = datetime.fromtimestamp(min(ts_list), tz=UTC).isoformat()
            info["newest_ts"] = datetime.fromtimestamp(max(ts_list), tz=UTC).isoformat()
    except (json.JSONDecodeError, OSError):
        pass
    return info
