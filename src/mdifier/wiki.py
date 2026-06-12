"""
Wiki页面获取模块

支持两种获取方式：
1. MediaWiki API - 优先使用，获取解析后的内容
2. HTML抓取 - 降级方案
"""

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

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
            raise ValueError(
                f"Unsupported language: {lang}. "
                f"Available: {list(LANG_CONFIG.keys())}"
            )
        self.lang = lang
        self.api_url = LANG_CONFIG[lang]["api"]
        self.base_url = LANG_CONFIG[lang]["base"]
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Minecraft-Wiki-MDifier/0.1.0 (Python Wiki Converter)"
        })

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

    def fetch_via_api(self, title: str) -> WikiPage | None:
        """
        通过MediaWiki API获取页面内容

        Args:
            title: 页面标题

        Returns:
            WikiPage对象，获取失败返回None
        """
        params = {
            "action": "parse",
            "page": title,
            "format": "json",
            "prop": "wikitext",
        }
        response = self.session.get(self.api_url, params=params)
        if response.status_code != 200:
            return None

        data = response.json()
        if "parse" not in data:
            return None

        parse_result = data["parse"]
        page_title = parse_result.get("title", title)
        wikitext = parse_result.get("wikitext", {}).get("*", "")

        return WikiPage(
            title=page_title,
            content=wikitext,
            source="api"
        )

    def fetch_via_html(self, title: str) -> WikiPage | None:
        """
        通过HTML抓取获取页面内容（降级方案）

        Args:
            title: 页面标题

        Returns:
            WikiPage对象，获取失败返回None
        """
        # 将标题转换为URL路径
        url_title = title.replace(" ", "_")
        url = f"{self.base_url}/{url_title}"

        response = self.session.get(url)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # 获取页面标题
        title_elem = soup.find("h1", id="firstHeading")
        page_title = title_elem.get_text(strip=True) if title_elem else title

        # 获取主要内容区域
        content_div = soup.find("div", id="mw-content-text")
        if not content_div:
            return None

        # 移除不需要的元素
        for elem in content_div.find_all(["script", "style", "noscript"]):
            elem.decompose()

        # 获取编辑按钮等无关元素
        for elem in content_div.find_all(class_=["navbox", "toc", "printfooter"]):
            elem.decompose()

        html_content = str(content_div)

        return WikiPage(
            title=page_title,
            content=html_content,
            source="html"
        )

    def fetch(self, title: str) -> WikiPage | None:
        """
        获取Wiki页面，优先使用API

        Args:
            title: 页面标题

        Returns:
            WikiPage对象
        """
        # 优先尝试API
        page = self.fetch_via_api(title)
        if page and page.content.strip():
            return page

        # API失败，降级到HTML抓取
        page = self.fetch_via_html(title)
        if page and page.content.strip():
            return page

        return None


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
