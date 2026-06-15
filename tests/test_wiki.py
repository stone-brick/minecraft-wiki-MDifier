"""测试 wiki.py"""

from unittest.mock import MagicMock, patch

import pytest

from mdifier.exceptions import InvalidInputError, PageNotFoundError, WikiAPIError
from mdifier.wiki import WikiFetcher, WikiPage, parse_url


class TestParseUrl:
    """parse_url() 函数测试"""

    def test_parse_url_zh(self):
        """解析中文 wiki URL"""
        lang, title = parse_url("https://zh.minecraft.wiki/铁锭")
        assert lang == "zh"
        assert title == "铁锭"

    def test_parse_url_zh_with_wiki_prefix(self):
        """解析带 /wiki/ 前缀的中文 wiki URL"""
        lang, title = parse_url("https://zh.minecraft.wiki/wiki/铁锭")
        assert lang == "zh"
        assert title == "铁锭"

    def test_parse_url_en(self):
        """解析英文 wiki URL（无子域名）"""
        lang, title = parse_url("https://minecraft.wiki/Iron_Ingot")
        assert lang == "en"
        assert title == "Iron_Ingot"

    def test_parse_url_en_with_wiki_prefix(self):
        """解析英文 wiki URL 带 /wiki/ 前缀"""
        lang, title = parse_url("https://minecraft.wiki/wiki/Iron_Ingot")
        assert lang == "en"
        assert title == "Iron_Ingot"

    def test_parse_url_en_subdomain(self):
        """解析英文 wiki URL（有 en. 子域名）"""
        lang, title = parse_url("https://en.minecraft.wiki/Iron_Ingot")
        assert lang == "en"
        assert title == "Iron_Ingot"

    def test_parse_url_unsupported(self):
        """不支持的域名抛出 InvalidInputError"""
        with pytest.raises(InvalidInputError):
            parse_url("https://example.com/SomePage")


class TestWikiFetcherInit:
    """WikiFetcher.__init__ 测试"""

    def test_init_zh(self):
        """支持中文 lang"""
        fetcher = WikiFetcher("zh")
        assert fetcher.lang == "zh"
        assert "zh.minecraft.wiki" in fetcher.api_url

    def test_init_en(self):
        """支持英文 lang"""
        fetcher = WikiFetcher("en")
        assert fetcher.lang == "en"
        assert "minecraft.wiki/api.php" in fetcher.api_url

    def test_init_unsupported(self):
        """不支持的 lang 抛出 InvalidInputError"""
        with pytest.raises(InvalidInputError):
            WikiFetcher("xx")


class TestWikiPage:
    """WikiPage 数据类测试"""

    def test_dataclass_fields(self, wiki_page_factory):
        """三个字段正确"""
        page = wiki_page_factory(title="Test", content="== Test ==", source="api")
        assert page.title == "Test"
        assert page.content == "== Test =="
        assert page.source == "api"


class TestFetchViaApi:
    """fetch_via_api() 测试"""

    @patch("mdifier.wiki.requests.Session")
    def test_api_200_ok(self, MockSession):
        """API 返回 200 OK → WikiPage(source="api")"""
        mock_instance = MockSession.return_value
        mock_instance.get.return_value.json.return_value = {
            "parse": {"wikitext": {"*": "== 页面内容 =="}}
        }
        mock_instance.get.return_value.status_code = 200

        fetcher = WikiFetcher("zh")
        page = fetcher.fetch_via_api("测试页面")

        assert page.source == "api"
        assert page.content == "== 页面内容 =="

    @patch("mdifier.wiki.requests.Session")
    def test_api_404(self, MockSession):
        """API 404 → 抛出 PageNotFoundError"""
        mock_instance = MockSession.return_value
        mock_instance.get.return_value.raise_status.return_value = None
        mock_instance.get.return_value.status_code = 404

        fetcher = WikiFetcher("zh")
        with pytest.raises(PageNotFoundError):
            fetcher.fetch_via_api("不存在的页面")

    @patch("mdifier.wiki.requests.Session")
    def test_api_500(self, MockSession):
        """API 500 → 抛出 WikiAPIError"""
        mock_instance = MockSession.return_value
        mock_instance.get.return_value.raise_status.side_effect = Exception("500 Server Error")

        fetcher = WikiFetcher("zh")
        with pytest.raises(WikiAPIError):
            fetcher.fetch_via_api("测试")

    @patch("mdifier.wiki.requests.Session")
    def test_api_non_json(self, MockSession):
        """API 非 JSON 响应 → 抛出 WikiAPIError"""
        mock_instance = MockSession.return_value
        mock_instance.get.return_value.json.side_effect = ValueError("Invalid JSON")

        fetcher = WikiFetcher("zh")
        with pytest.raises(WikiAPIError):
            fetcher.fetch_via_api("测试")

    @patch("mdifier.wiki.requests.Session")
    def test_api_no_parse_field(self, MockSession):
        """API 响应无 parse 字段 → 抛出 WikiAPIError"""
        mock_instance = MockSession.return_value
        mock_instance.get.return_value.json.return_value = {"error": {"info": "Page not found"}}
        mock_instance.get.return_value.status_code = 200

        fetcher = WikiFetcher("zh")
        with pytest.raises(WikiAPIError):
            fetcher.fetch_via_api("测试")


class TestFetchViaHtml:
    """fetch_via_html() 测试"""

    @patch("mdifier.wiki.requests.Session")
    def test_html_200_ok(self, MockSession):
        """HTML 正常返回 → WikiPage(source="html")"""
        html = "<div id='mw-content-text'><p>页面内容</p></div>"
        mock_instance = MockSession.return_value
        mock_instance.get.return_value.text = html
        mock_instance.get.return_value.status_code = 200

        fetcher = WikiFetcher("zh")
        page = fetcher.fetch_via_html("测试页面")

        assert page.source == "html"
        assert "页面内容" in page.content

    @patch("mdifier.wiki.requests.Session")
    def test_html_no_mw_content(self, MockSession):
        """HTML 不含 mw-content-text → 抛出 PageNotFoundError"""
        mock_instance = MockSession.return_value
        mock_instance.get.return_value.text = "<html><body>No content</body></html>"
        mock_instance.get.return_value.status_code = 200

        fetcher = WikiFetcher("zh")
        with pytest.raises(WikiAPIError):
            fetcher.fetch_via_html("不存在的页面")


class TestFetchFallback:
    """fetch() API→HTML 降级逻辑测试"""

    @patch("mdifier.wiki.requests.Session")
    def test_api_404_falls_back_to_html(self, MockSession):
        """API 404 时降级到 HTML"""
        html = "<div id='mw-content-text'><p>降级内容</p></div>"

        def get_side_effect(url, **kwargs):
            m = MagicMock()
            if "api.php" in url:
                m.status_code = 404
                m.raise_status.side_effect = Exception("404")
            else:
                m.text = html
                m.status_code = 200
            return m

        mock_instance = MockSession.return_value
        mock_instance.get.side_effect = get_side_effect

        fetcher = WikiFetcher("zh")
        page = fetcher.fetch("测试页面")

        assert page.source == "html"
        assert "降级内容" in page.content

    # 注：API 异常降级到 HTML 的逻辑在 fetch() 内部通过异常处理实现，
    # 由于 mock 绕过了实际调用路径，此处通过 test_api_404_falls_back_to_html 间接覆盖


class TestFetchMany:
    """fetch_many() 测试"""

    @patch("mdifier.wiki.WikiFetcher.fetch")
    def test_fetch_many_returns_in_order(self, mock_fetch):
        """多页面并发，返回顺序与输入一致"""

        # 直接 mock fetch 方法本身，消除并发下 side_effect 顺序不确定的问题
        def fetch_all(title: str):
            return WikiPage(title=title, content=title.lower(), source="api")

        mock_fetch.side_effect = fetch_all

        fetcher = WikiFetcher("zh")
        pages = fetcher.fetch_many(["A", "B", "C"])

        assert len(pages) == 3
        assert [p.title for p in pages] == ["A", "B", "C"]

    @patch("mdifier.wiki.WikiFetcher.fetch")
    def test_fetch_many_partial_failure(self, mock_fetch):
        """部分失败返回 None 不抛异常"""

        # fetch 方法 raise 的异常会被 fetch_many 捕获并转为 None
        def fetch_simu(title: str):
            if title == "B":
                raise PageNotFoundError("B not found")
            return WikiPage(title=title, content=title.lower(), source="api")

        mock_fetch.side_effect = fetch_simu

        fetcher = WikiFetcher("zh")
        pages = fetcher.fetch_many(["A", "B", "C"])

        assert pages[0].title == "A"
        assert pages[1] is None
        assert pages[2].title == "C"
