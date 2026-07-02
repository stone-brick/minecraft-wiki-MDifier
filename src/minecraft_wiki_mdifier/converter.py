"""
Markdown 转换器

Wikitext → pypandoc 预处理 → 模板展开 → 渲染
"""

import base64
import logging
import threading

from minecraft_wiki_mdifier import pandoc_trimmer
from minecraft_wiki_mdifier.template_expander import TemplateExpander
from minecraft_wiki_mdifier.wiki import WikiPage

_logger = logging.getLogger(__name__)


def _encode_cache_value(v: str) -> str:
    """URL-safe base64 编码，避免分隔符冲突（"|" 和 "=" 不会出现在编码结果中）。"""
    return base64.urlsafe_b64encode(v.encode("utf-8")).decode("ascii")


class MarkdownConverter:
    """Markdown 转换器（精简包装器）"""

    def __init__(
        self,
        lang: str = "zh",
        max_workers: int = 10,
        template_cache: dict | None = None,
        use_persistent_cache: bool = True,
    ):
        self.lang = lang
        self.max_workers = max_workers
        self._use_persistent_cache = use_persistent_cache
        # 跨页共享的模板缓存（外部注入实现多批次共享）
        if template_cache is not None:
            self._template_cache = template_cache
        elif use_persistent_cache:
            from minecraft_wiki_mdifier.cache import load_cache

            self._template_cache = load_cache()
        else:
            self._template_cache = {}
        self._cache_lock = threading.Lock()
        # 未展开的模板名（驼峰映射缺失或模板不存在）
        self._unresolved: set[str] = set()
        self._unresolved_lock = threading.Lock()
        # 取消标志（convert_many 检查）
        self._cancelled = False
        self._cancel_lock = threading.Lock()
        self.expander = TemplateExpander(
            lang=lang,
            template_cache=self._template_cache,
            cache_lock=self._cache_lock,
        )

    def cancel(self) -> None:
        """请求取消批量转换（仅 convert_many 有效）"""
        with self._cancel_lock:
            self._cancelled = True

    @property
    def unresolved_templates(self) -> frozenset[str]:
        return frozenset(self._unresolved)

    def is_cancelled(self) -> bool:
        with self._cancel_lock:
            return self._cancelled

    def flush_cache(self) -> None:
        if not self._use_persistent_cache:
            return
        from minecraft_wiki_mdifier.cache import save_cache

        with self._cache_lock:
            save_cache(self._template_cache)

    def convert_wiki(self, page: WikiPage) -> str:
        return self._convert_wikitext(page.content, page.title)

    def _convert_wikitext(self, wikitext: str, title: str) -> str:
        return pandoc_trimmer.wikitext_to_format(
            wikitext, self.expander, title, "commonmark_x", self.lang
        )
