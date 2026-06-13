"""共享 fixtures"""

from unittest.mock import MagicMock

import pytest

from mdifier.wiki import WikiPage


@pytest.fixture
def wiki_page_factory():
    """构造测试 WikiPage"""
    def _make(title: str = "测试页面", content: str = "{{Hatnote|test}}", source: str = "api") -> WikiPage:
        return WikiPage(title=title, content=content, source=source)
    return _make


@pytest.fixture
def expander_mock():
    """TemplateExpander mock，返回标准展开结果"""
    mock = MagicMock()
    mock.expand.return_value = {
        "html": "<div class='hatnote'>test</div>",
        "class": "hatnote",
        "text": "test",
        "format": "text",
        "table": None,
    }
    return mock


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """把缓存目录临时重定向到 tmp_path"""
    from mdifier import cache as cache_mod
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache_mod, "CACHE_FILE", tmp_path / "templates.json")
    return tmp_path
