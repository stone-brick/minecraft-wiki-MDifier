"""
库模式API

提供Python库方式使用的接口
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from itertools import count

from mdifier.cache import get_or_load_persistent_cache, save_cache
from mdifier.converter import MarkdownConverter
from mdifier.exceptions import InvalidInputError
from mdifier.wiki import LANG_CONFIG, WikiFetcher, WikiPage, parse_url


@dataclass
class ConvertResult:
    """转换结果"""

    title: str  # 页面标题
    markdown: str  # Markdown内容
    source: str  # 数据来源 "api" 或 "html"
    templates: dict  # 提取的模板数据


def _resolve_and_fetch(title_or_url: str, lang: str | None) -> tuple[WikiPage, str]:
    """共享的 lang 验证 + URL 解析 + fetch。返回 (page, resolved_lang)。"""
    if lang is not None and lang not in LANG_CONFIG:
        raise InvalidInputError(
            f"Unsupported language: {lang}. Available: {list(LANG_CONFIG.keys())}"
        )
    if title_or_url.startswith("http"):
        parsed_lang, title = parse_url(title_or_url)
        if lang is None:
            lang = parsed_lang
    else:
        title = title_or_url
        if lang is None:
            lang = "zh"
    fetcher = WikiFetcher(lang=lang)
    page = fetcher.fetch(title)
    if page is None:
        raise InvalidInputError(f"无法获取页面: {title}")
    return page, lang


def convert(
    title_or_url: str,
    lang: str | None = None,
    template_cache: dict | None = None,
) -> str:
    """
    将Minecraft Wiki页面转换为Markdown

    注意：批量转换请用 convert_many（共享模板缓存 + 并发优化）。

    Args:
        title_or_url: 页面标题或完整URL
        lang: 语言，'zh'或'en'，None则自动检测
        template_cache: 跨调用共享的模板缓存（None 则新建空 dict）
            不会自动持久化到磁盘（用 convert_many 才有）

    Returns:
        Markdown格式字符串

    Example:
        >>> from mdifier import convert
        >>> md = convert("铁锭")
        >>> print(md)

        >>> # 跨调用共享缓存
        >>> shared = {}
        >>> convert("钻石", template_cache=shared)
        >>> convert("铁锭", template_cache=shared)  # 共享
    """
    page, lang = _resolve_and_fetch(title_or_url, lang)
    converter = MarkdownConverter(lang=lang, template_cache=template_cache)
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
    page, lang = _resolve_and_fetch(title_or_url, lang)
    converter = MarkdownConverter(lang=lang)
    markdown = converter.convert_wiki(page)
    return ConvertResult(title=page.title, markdown=markdown, source=page.source, templates={})


@dataclass
class BatchConvertResult:
    """批量转换结果"""

    results: list[ConvertResult]  # 顺序与输入一致（失败的项为 None）
    failed: list[tuple[str, str]]  # (title, error_message)
    unresolved: list[str] = field(default_factory=list)  # 未展开的模板名（驼峰缺失）


def _convert_one(converter: MarkdownConverter, page: WikiPage | None, title: str) -> ConvertResult:
    """单页转换辅助函数（供 ThreadPoolExecutor 调用）"""
    if page is None:
        raise InvalidInputError(f"无法获取页面: {title}")
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
    converter_factory: Callable[[str, dict | None], MarkdownConverter] | None = None,
) -> BatchConvertResult:
    """
    批量转换 Wiki 页面

    Args:
        items: 标题或 URL 列表（可混合）
        lang: 默认语言
        max_workers: 跨页并发抓取数
        on_progress: 进度回调 (done, total, title)
        template_cache: 跨批次共享的模板缓存（None 则内部新建）
        converter_factory: 自定义 converter 工厂 (lang, cache) -> MarkdownConverter
            用于获得 converter 引用（如想从外部调用 cancel()）

    Returns:
        BatchConvertResult，含 results 和 failed 列表

    Example:
        >>> from mdifier import convert_many
        >>> result = convert_many(["钻石", "铁锭", "附魔台"])
        >>> for r in result.results:
        ...     print(f"=== {r.title} ===")

        >>> # 外部引用 converter 实现取消
        >>> import threading
        >>> from mdifier.converter import MarkdownConverter
        >>> c = MarkdownConverter(lang='zh')
        >>> threading.Timer(0.5, c.cancel).start()
        >>> convert_many(['钻石'], converter_factory=lambda l, cache: c)
    """
    if lang not in LANG_CONFIG:
        raise InvalidInputError(
            f"Unsupported language: {lang}. Available: {list(LANG_CONFIG.keys())}"
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

    # 默认 converter 工厂
    def default_factory(item_lang: str, cache: dict | None) -> MarkdownConverter:
        return MarkdownConverter(lang=item_lang, template_cache=cache)

    factory = converter_factory or default_factory

    # 3. 每 lang 一次会话
    final_results: list[ConvertResult | None] = [None] * len(items)
    final_failed: list[tuple[str, str]] = []
    all_unresolved: dict[str, int] = {}  # {模板名: 首次出现索引}
    done_counter = count(1)

    for group_lang, group in by_lang.items():
        fetcher = WikiFetcher(lang=group_lang)
        # 用用户工厂或默认工厂创建 converter
        cache = template_cache if template_cache is not None else get_or_load_persistent_cache()
        converter = factory(group_lang, cache)
        titles = [t for _, t in group]

        # 跨页并发抓取
        pages = fetcher.fetch_many(titles, max_workers=max_workers)

        # 跨页并发转换（每页 1 线程，模板展开内部有 10 workers）
        with ThreadPoolExecutor(max_workers=2) as ex:
            future_map = {
                ex.submit(_convert_one, converter, page, t): (i, t)
                for (i, t), page in zip(group, pages, strict=True)
            }
            for future in as_completed(future_map):
                if converter._cancelled:
                    # 取消：取消剩余 futures
                    for remaining in future_map:
                        remaining.cancel()
                    break
                idx, t = future_map[future]
                try:
                    final_results[idx] = future.result()
                except Exception as e:
                    # 含异常类型名，方便用户定位问题
                    final_failed.append((t, f"{type(e).__name__}: {e}"))
                done = next(done_counter)
                if on_progress:
                    on_progress(done, len(items), t)
        # 收集 unresolved（保持插入序，首现优先）
        for tmpl in converter._unresolved:
            if tmpl not in all_unresolved:
                all_unresolved[tmpl] = 0

    # 批量结束只 flush 一次（用户没传 cache 时）
    if template_cache is None:
        save_cache(cache)

    return BatchConvertResult(
        results=[r for r in final_results if r is not None],
        failed=final_failed,
        unresolved=list(all_unresolved),
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
