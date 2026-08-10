"""
配置文件管理

优先级（低→高）：代码默认值 < 配置文件 < 环境变量 MDIFFER_* < 显式传参
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

CONFIG_PATH = (
    Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "mdifier" / "config.toml"
)

# 可配置项及类型（用于类型自动推断和验证）
CONFIG_KEYS: dict[str, type] = {
    "lang": str,
    "variant": str,
    "workers": int,
    "output_dir": str,
    "marker_format": str,
    "no_markers": bool,
}

# 代码默认值
DEFAULT_CONFIG: dict[str, Any] = {
    "lang": "zh",
    "variant": None,  # None 表示使用 lang 对应的内置默认值
    "workers": 4,
    "output_dir": None,
    "marker_format": None,  # None 表示使用 converter 默认
    "no_markers": False,
}


def _infer_type(value: str) -> Any:
    """将字符串自动推断为合理类型"""
    if value.lower() in ("true", "yes", "1"):
        return True
    if value.lower() in ("false", "no", "0"):
        return False
    if value.isdigit():
        return int(value)
    return value


def load_config() -> dict[str, Any]:
    """
    加载配置，合并三层：
    默认值 < 配置文件 < 环境变量 MDIFFER_*
    """
    config = DEFAULT_CONFIG.copy()

    # 1. 读配置文件
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            file_config = tomllib.load(f)
        if "defaults" in file_config:
            for key in CONFIG_KEYS:
                if key in file_config["defaults"]:
                    config[key] = file_config["defaults"][key]

    # 2. 环境变量覆盖（仅已定义的 key）
    for key in CONFIG_KEYS:
        env_val = os.getenv(f"MDIFFER_{key.upper()}")
        if env_val is not None:
            config[key] = _infer_type(env_val)

    return config


def get_config_source() -> dict[str, str]:
    """
    返回每个 key 的实际来源：'default' | 'file' | 'env'
    """
    sources: dict[str, str] = {}
    config = DEFAULT_CONFIG.copy()

    # 文件层
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            file_config = tomllib.load(f)
        if "defaults" in file_config:
            for key in CONFIG_KEYS:
                if key in file_config["defaults"]:
                    config[key] = file_config["defaults"][key]
                    sources[key] = "file"

    # 环境变量层（优先级最高）
    for key in CONFIG_KEYS:
        if os.getenv(f"MDIFFER_{key.upper()}") is not None:
            sources[key] = "env"
            config[key] = _infer_type(os.getenv(f"MDIFFER_{key.upper()}"))

    # 填充未设置的 key
    for key in CONFIG_KEYS:
        if key not in sources:
            sources[key] = "default"

    return sources


def save_config(key: str, value: Any) -> None:
    """
    保存配置项到文件，类型自动推断。
    key 必须是 CONFIG_KEYS 中定义的项。
    """
    if key not in CONFIG_KEYS:
        raise ValueError(f"未知的配置项: {key}")

    # 自动类型推断
    if isinstance(value, str):
        value = _infer_type(value)

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 读出现有配置
    existing: dict[str, dict[str, Any]] = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            existing = tomllib.load(f)

    existing.setdefault("defaults", {})[key] = value

    # 手动写 TOML（避免引入 tomli-w 写依赖）
    lines = ["[defaults]\n"]
    for k, v in existing["defaults"].items():
        if isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}\n")
        elif isinstance(v, int):
            lines.append(f"{k} = {v}\n")
        elif isinstance(v, str):
            lines.append(f'{k} = "{v}"\n')
        else:
            lines.append(f"{k} = {v}\n")
    CONFIG_PATH.write_text("".join(lines), encoding="utf-8")
