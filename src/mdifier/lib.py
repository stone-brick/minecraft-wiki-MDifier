"""
库模式API

提供Python库方式使用的接口
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from mdifier.converter import MarkdownConverter
from mdifier.wiki import LANG_CONFIG, WikiFetcher, parse_url


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
    # 验证 lang
    if lang is not None and lang not in LANG_CONFIG:
        raise ValueError(
            f"Unsupported language: {lang}. "
            f"Available: {list(LANG_CONFIG.keys())}"
        )

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
    # 验证 lang
    if lang is not None and lang not in LANG_CONFIG:
        raise ValueError(
            f"Unsupported language: {lang}. "
            f"Available: {list(LANG_CONFIG.keys())}"
        )

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


@dataclass
class BatchConvertResult:
    """批量转换结果"""
    results: list[ConvertResult]            # 顺序与输入一致（失败的项为 None）
    failed: list[tuple[str, str]]           # (title, error_message)
    unresolved: list[str] = field(default_factory=list)  # 未展开的模板名（驼峰缺失）


def _convert_one(
    converter: MarkdownConverter, page: object, title: str
) -> ConvertResult:
    """单页转换辅助函数（供 ThreadPoolExecutor 调用）"""
    if page is None:
        raise ValueError(f"无法获取页面: {title}")
    return ConvertResult(
        title=page.title,
        markdown=converter.convert_wiki(page),
        source=page.source,
        templates={},
    )


def convert_many(
    items: list[str],
    lang: str = "zh",
    max_workers: int = 4,
    on_progress: Callable[[int, int, str], None] | None = None,
    template_cache: dict | None = None,
) -> BatchConvertResult:
    """
    批量转换 Wiki 页面

    Args:
        items: 标题或 URL 列表（可混合）
        lang: 默认语言
        max_workers: 跨页并发抓取数
        on_progress: 进度回调 (done, total, title)
        template_cache: 跨批次共享的模板缓存（None 则内部新建）

    Returns:
        BatchConvertResult，含 results 和 failed 列表

    Example:
        >>> from mdifier import convert_many
        >>> result = convert_many(["钻石", "铁锭", "附魔台"])
        >>> for r in result.results:
        ...     print(f"=== {r.title} ===")
    """
    if lang not in LANG_CONFIG:
        raise ValueError(
            f"Unsupported language: {lang}. "
            f"Available: {list(LANG_CONFIG.keys())}"
        )

    # 1. 归一化输入：URL → (lang, title)
    parsed: list[tuple[str, str]] = []
    for it in items:
        if it.startswith("http"):
            parsed_lang, title = parse_url(it)
            # 用户显式指定 lang 时优先
            if parsed_lang and parsed_lang != lang:
                parsed.append((lang, title))
            else:
                parsed.append((parsed_lang, title))
        else:
            parsed.append((lang, it))

    # 2. 按 lang 分组
    by_lang: dict[str, list[tuple[int, str]]] = {}
    for idx, (item_lang, t) in enumerate(parsed):
        by_lang.setdefault(item_lang, []).append((idx, t))

    # 3. 每 lang 一次会话
    final_results: list[ConvertResult | None] = [None] * len(items)
    final_failed: list[tuple[str, str]] = []
    done, total = 0, len(items)

    for group_lang, group in by_lang.items():
        fetcher = WikiFetcher(lang=group_lang)
        converter = MarkdownConverter(lang=group_lang, template_cache=template_cache)
        titles = [t for _, t in group]

        # 跨页并发抓取
        pages = fetcher.fetch_many(titles, max_workers=max_workers)

        # 跨页并发转换（每页 1 线程，模板展开内部有 10 workers）
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_map = {
                ex.submit(_convert_one, converter, page, t): (i, t)
                for (i, t), page in zip(group, pages, strict=True)
            }
            for fut in as_completed(fut_map):
                idx, t = fut_map[fut]
                try:
                    final_results[idx] = fut.result()
                except Exception as e:
                    final_failed.append((t, str(e)))
                done += 1
                if on_progress:
                    on_progress(done, total, t)

    # 保存模板缓存到磁盘（跨运行共享）；仅在用户没传 cache 时持久化
    if template_cache is None:
        converter.flush_cache()

    return BatchConvertResult(
        results=[r for r in final_results if r is not None],
        failed=final_failed,
        unresolved=sorted(converter._unresolved),
    )


def search(query: str, lang: str = "zh") -> list[dict]:
    """
    搜索Minecraft Wiki页面

    Args:
        query: 搜索关键词
        lang: 语言，'zh' 或 'en'

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


__all__ = [
    "BatchConvertResult",
    "ConvertResult",
    "convert",
    "convert_detailed",
    "convert_many",
    "search",
]
