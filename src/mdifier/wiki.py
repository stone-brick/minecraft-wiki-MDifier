"""
Wiki页面获取模块

支持两种获取方式：
1. MediaWiki API - 优先使用，获取解析后的内容
2. HTML抓取 - 降级方案
"""

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from mdifier.exceptions import (
    InvalidInputError,
    NetworkError,
    PageNotFoundError,
    WikiAPIError,
)

# 语言配置：集中管理 URL 和解析模式
LANG_CONFIG: dict[str, dict[str, str]] = {
    "zh": {
        "api": "https://zh.minecraft.wiki/api.php",
        "base": "https://zh.minecraft.wiki",
    },
    "en": {
        "api": "https://minecraft.wiki/api.php",
        "base": "https://minecraft.wiki",
    },
}

# URL 解析模式：(正则, 匹配的语言)
# 注意：MediaWiki 默认 URL 是 /wiki/{title}，但用户可能省略 /wiki/
URL_PATTERNS: list[tuple[str, str]] = [
    (r"https?://zh\.minecraft\.wiki/(?:wiki/)?(?P<title>.+)", "zh"),
    (r"https?://minecraft\.wiki/(?:wiki/)?(?P<title>.+)", "en"),
    (r"https?://en\.minecraft\.wiki/(?:wiki/)?(?P<title>.+)", "en"),
]


@dataclass
class WikiPage:
    """Wiki页面数据类"""

    title: str
    content: str  # 解析后的wikitext或HTML
    source: str  # "api" 或 "html"


class WikiFetcher:
    """Wiki页面获取器"""

    def __init__(self, lang: str = "zh"):
        if lang not in LANG_CONFIG:
            raise InvalidInputError(
                f"Unsupported language: {lang}. Available: {list(LANG_CONFIG.keys())}"
            )
        self.lang = lang
        self.api_url = LANG_CONFIG[lang]["api"]
        self.base_url = LANG_CONFIG[lang]["base"]
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Minecraft-Wiki-MDifier/0.1.0 (Python Wiki Converter)"}
        )

    def search(self, query: str) -> list[dict]:
        """
        搜索Wiki页面

        Args:
            query: 搜索关键词

        Returns:
            搜索结果列表
        """
        params = {
            "action": "opensearch",
            "search": query,
            "limit": "10",
            "namespace": "0",
            "format": "json",
        }
        response = self.session.get(self.api_url, params=params)
        response.raise_for_status()
        data = response.json()

        # 返回格式: [query, [titles], [descriptions], [urls]]
        if len(data) >= 4:
            titles = data[1]
            descriptions = data[2]
            urls = data[3]
            return [
                {"title": t, "description": d, "url": u}
                for t, d, u in zip(titles, descriptions, urls, strict=False)
            ]
        return []

    def fetch_via_api(self, title: str) -> WikiPage:
        """
        通过MediaWiki API获取页面内容

        Args:
            title: 页面标题

        Returns:
            WikiPage对象

        Raises:
            NetworkError: 网络连接失败
            PageNotFoundError: 页面不存在（API 404）
            WikiAPIError: API 返回异常结构
        """
        params = {
            "action": "parse",
            "page": title,
            "format": "json",
            "prop": "wikitext",
        }
        try:
            response = self.session.get(self.api_url, params=params, timeout=10)
        except requests.RequestException as e:
            raise NetworkError(f"无法连接 {self.api_url}: {e}") from e

        if response.status_code == 404:
            raise PageNotFoundError(f"页面不存在（API 404）: {title}")
        if response.status_code != 200:
            raise WikiAPIError(f"API 返回 {response.status_code}: {title}")

        try:
            data = response.json()
        except ValueError as e:
            raise WikiAPIError(f"API 返回非 JSON 数据: {title}") from e

        if "parse" not in data:
            raise WikiAPIError(f"API 返回无 parse 字段: {title}")

        parse_result = data["parse"]
        page_title = parse_result.get("title", title)
        wikitext = parse_result.get("wikitext", {}).get("*", "")

        return WikiPage(title=page_title, content=wikitext, source="api")

    def fetch_via_html(self, title: str) -> WikiPage:
        """
        通过HTML抓取获取页面内容（降级方案）

        Args:
            title: 页面标题

        Returns:
            WikiPage对象

        Raises:
            NetworkError: 网络连接失败
            PageNotFoundError: 页面不存在（HTTP 404）
            WikiAPIError: HTML 解析失败
        """
        # 将标题转换为URL路径
        url_title = title.replace(" ", "_")
        url = f"{self.base_url}/{url_title}"

        try:
            response = self.session.get(url, timeout=10)
        except requests.RequestException as e:
            raise NetworkError(f"无法连接 {url}: {e}") from e

        if response.status_code == 404:
            raise PageNotFoundError(f"页面不存在（HTTP 404）: {title}")
        if response.status_code != 200:
            raise WikiAPIError(f"HTML 返回 {response.status_code}: {title}")

        soup = BeautifulSoup(response.text, "html.parser")

        # 获取页面标题
        title_elem = soup.find("h1", id="firstHeading")
        page_title = title_elem.get_text(strip=True) if title_elem else title

        # 获取主要内容区域
        content_div = soup.find("div", id="mw-content-text")
        if not content_div:
            raise WikiAPIError(f"HTML 无 mw-content-text 区域: {title}")

        # 移除不需要的元素
        for elem in content_div.find_all(["script", "style", "noscript"]):
            elem.decompose()

        # 获取编辑按钮等无关元素
        for elem in content_div.find_all(class_=["navbox", "toc", "printfooter"]):
            elem.decompose()

        html_content = str(content_div)

        return WikiPage(title=page_title, content=html_content, source="html")

    def fetch(self, title: str) -> WikiPage:
        """
        获取Wiki页面，优先使用API

        Args:
            title: 页面标题

        Returns:
            WikiPage对象

        Raises:
            NetworkError: 网络层失败
            PageNotFoundError: API 和 HTML 都返回 404
            WikiAPIError: API 和 HTML 都返回异常
        """
        # 优先尝试 API
        try:
            page = self.fetch_via_api(title)
            if page and page.content.strip():
                return page
        except PageNotFoundError:
            # 404 时降级到 HTML 抓取
            pass
        except NetworkError:
            # 网络错误不重试
            raise
        except requests.RequestException as e:
            # 兜底：未预期的 requests 异常 → 包装为 NetworkError
            raise NetworkError(f"网络请求失败: {e}") from e
        except WikiAPIError:
            # API 异常，降级到 HTML
            pass

        # API 失败或返回空，降级到 HTML 抓取
        try:
            page = self.fetch_via_html(title)
            if page and page.content.strip():
                return page
        except NetworkError:
            raise
        except requests.RequestException as e:
            raise NetworkError(f"网络请求失败: {e}") from e

        # HTML 也没拿到内容
        raise PageNotFoundError(f"页面不存在或内容为空: {title}")

    def fetch_many(
        self,
        titles: list[str],
        max_workers: int = 4,
        on_progress: Callable[[str, WikiPage | None], None] | None = None,
    ) -> list[WikiPage | None]:
        """
        并发获取多个页面；保持输入顺序；失败位置为 None

        Args:
            titles: 页面标题列表
            max_workers: 并发抓取数
            on_progress: 进度回调 (title, page_or_none)

        Returns:
            与输入等长的列表，失败位置为 None
        """
        results: list[WikiPage | None] = [None] * len(titles)
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            future_to_idx = {ex.submit(self.fetch, t): i for i, t in enumerate(titles)}
            for fut in as_completed(future_to_idx):
                i = future_to_idx[fut]
                try:
                    results[i] = fut.result()
                except Exception:
                    results[i] = None
                if on_progress:
                    on_progress(titles[i], results[i])
        return results


def parse_url(url: str) -> tuple[str, str]:
    """
    从URL中解析出语言和页面标题

    Args:
        url: Wiki页面URL

    Returns:
        (lang, title) 元组
    """
    for pattern, lang in URL_PATTERNS:
        match = re.match(pattern, url)
        if match:
            title = match.group("title")
            # URL解码
            title = requests.utils.unquote(title)
            return lang, title

    return "zh", url


def convert(title_or_url: str, lang: str | None = None) -> WikiPage | None:
    """
    便捷函数：获取Wiki页面

    Args:
        title_or_url: 页面标题或URL
        lang: 语言，None则自动从URL解析

    Returns:
        WikiPage对象
    """
    if title_or_url.startswith("http"):
        parsed_lang, title = parse_url(title_or_url)
        if lang is None:
            lang = parsed_lang
    else:
        title = title_or_url
        if lang is None:
            lang = "zh"

    fetcher = WikiFetcher(lang=lang)
    return fetcher.fetch(title)
