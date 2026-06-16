"""
Minecraft Wiki MDifier

将Minecraft Wiki页面转换为AI助手易读的Markdown格式。
"""

__version__ = "0.1.2"

from minecraft_wiki_mdifier.lib import (
    BatchConvertResult,
    ConvertResult,
    convert,
    convert_detailed,
    convert_many,
    search,
)

__all__ = [
    "BatchConvertResult",
    "ConvertResult",
    "convert",
    "convert_detailed",
    "convert_many",
    "search",
    "__version__",
]
