"""
Minecraft Wiki MDifier

将Minecraft Wiki页面转换为AI助手易读的Markdown格式。
"""

__version__ = "0.1.0"

from mdifier.lib import convert, convert_detailed, search

__all__ = ["convert", "convert_detailed", "search", "__version__"]
