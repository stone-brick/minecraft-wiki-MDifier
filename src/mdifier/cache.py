"""
模板展开结果缓存（持久化）

将跨页模板展开结果保存到磁盘，避免重复 API 请求。

存储位置：~/.cache/mdifier/templates.json
有效期：7 天（wiki 内容会更新）
"""

import json
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "mdifier"
CACHE_FILE = CACHE_DIR / "templates.json"

# 缓存有效期（7 天，wiki 内容会更新）
CACHE_TTL = 7 * 24 * 3600


def load_cache() -> dict:
    """从磁盘加载缓存；过期或不存在则返回空 dict

    Returns:
        {cache_key: {name, class, text, html, format, table, _ts}}
    """
    if not CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        now = time.time()
        # 过滤过期项
        return {
            k: v for k, v in data.items()
            if now - v.get("_ts", 0) < CACHE_TTL
        }
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache: dict) -> None:
    """保存缓存到磁盘（添加时间戳用于 TTL）

    Args:
        cache: 模板缓存 dict
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    enriched = {k: {**v, "_ts": time.time()} for k, v in cache.items()}
    CACHE_FILE.write_text(
        json.dumps(enriched, ensure_ascii=False),
        encoding="utf-8"
    )
