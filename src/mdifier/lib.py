"""
库模式API

提供Python库方式使用的接口
"""

from dataclasses import dataclass

from mdifier.wiki import WikiFetcher, WikiPage, parse_url
from mdifier.converter import MarkdownConverter


@dataclass
class ConvertResult:
    """转换结果"""
    title: str  # 页面标题
    markdown: str  # Markdown内容
    source: str  # 数据来源 "api" 或 "html"
    templates: dict  # 提取的模板数据


def convert(
    title_or_url: str,
    lang: str | None = None
) -> str:
    """
    将Minecraft Wiki页面转换为Markdown

    Args:
        title_or_url: 页面标题或完整URL
        lang: 语言，'zh'或'en'，None则自动检测

    Returns:
        Markdown格式字符串

    Example:
        >>> from mdifier import convert
        >>> md = convert("铁锭")
        >>> print(md)
    """
    # 解析输入
    if title_or_url.startswith("http"):
        parsed_lang, title = parse_url(title_or_url)
        if lang is None:
            lang = parsed_lang
    else:
        title = title_or_url
        if lang is None:
            lang = "zh"

    # 获取页面
    fetcher = WikiFetcher(lang=lang)
    page = fetcher.fetch(title)

    if page is None:
        raise ValueError(f"无法获取页面: {title}")

    # 转换
    converter = MarkdownConverter(lang=lang)
    return converter.convert_wiki(page)


def convert_detailed(title_or_url: str, lang: str | None = None) -> ConvertResult:
    """
    将Minecraft Wiki页面转换为Markdown，并返回详细信息

    Args:
        title_or_url: 页面标题或完整URL
        lang: 语言，'zh'或'en'，None则自动检测

    Returns:
        ConvertResult对象，包含标题、Markdown、来源和模板数据

    Example:
        >>> from mdifier import convert_detailed
        >>> result = convert_detailed("铁锭")
        >>> print(result.title)
        >>> print(result.markdown)
        >>> print(result.templates)
    """
    # 解析输入
    if title_or_url.startswith("http"):
        parsed_lang, title = parse_url(title_or_url)
        if lang is None:
            lang = parsed_lang
    else:
        title = title_or_url
        if lang is None:
            lang = "zh"

    # 获取页面
    fetcher = WikiFetcher(lang=lang)
    page = fetcher.fetch(title)

    if page is None:
        raise ValueError(f"无法获取页面: {title}")

    # 转换
    converter = MarkdownConverter(lang=lang)
    markdown = converter.convert_wiki(page)

    return ConvertResult(
        title=page.title,
        markdown=markdown,
        source=page.source,
        templates={}
    )


def search(query: str, lang: str = "zh") -> list[dict]:
    """
    搜索Minecraft Wiki页面

    Args:
        query: 搜索关键词
        lang: 语言，'zh'或'en'

    Returns:
        搜索结果列表，每项包含title、description、url

    Example:
        >>> from mdifier import search
        >>> results = search("diamond")
        >>> for r in results:
        >>>     print(r['title'])
    """
    fetcher = WikiFetcher(lang=lang)
    return fetcher.search(query)


__all__ = ["convert", "convert_detailed", "search"]
