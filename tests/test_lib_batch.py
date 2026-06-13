"""测试 convert_many 编排（mock WikiFetcher）"""

from types import SimpleNamespace
from unittest.mock import patch

from mdifier.wiki import WikiPage


def _make_page(title: str, content: str = "{{Hatnote|x}}") -> WikiPage:
    return WikiPage(title=title, content=content, source="api")


def _make_convert_result(title: str) -> SimpleNamespace:
    """构造 ConvertResult-like 对象（SimpleNamespace 替代）"""
    return SimpleNamespace(title=title, markdown=f"#{title}\nbody", source="api", templates={})


class TestConvertMany:
    def test_lang_validation(self):
        """不支持的 lang 抛 InvalidInputError"""
        from mdifier import convert_many
        from mdifier.exceptions import InvalidInputError

        try:
            convert_many(["X"], lang="xx")
        except InvalidInputError as e:
            assert "xx" in str(e)
        else:
            raise AssertionError("应该抛 InvalidInputError")

    def test_dedup(self):
        """重复标题不去重——dedup 在 CLI 层"""
        from mdifier import convert_many

        with patch("mdifier.lib.WikiFetcher") as MF, patch("mdifier.lib._convert_one") as CO:

            def mock_fetch(titles, **kwargs):
                return [_make_page(t) for t in titles]

            MF.return_value.fetch_many.side_effect = mock_fetch
            CO.side_effect = lambda c, p, t: _make_convert_result(t)
            # convert_many 本身不去重（CLI batch_cmd 负责去重）
            result = convert_many(["A", "A", "B", "A"])
            # 4 次调用 _convert_one（不去重）
            assert CO.call_count == 4
            assert len(result.results) == 4

    def test_failed_aggregation(self):
        """失败页面聚合到 result.failed，含异常类型名"""
        from mdifier import convert_many

        with patch("mdifier.lib.WikiFetcher") as MF, patch("mdifier.lib._convert_one") as CO:

            def mock_fetch(titles, **kwargs):
                return [_make_page(t) for t in titles]

            MF.return_value.fetch_many.side_effect = mock_fetch

            def mock_convert(c, p, t):
                if t == "BAD":
                    raise ValueError("测试失败")
                return _make_convert_result(t)

            CO.side_effect = mock_convert
            result = convert_many(["GOOD", "BAD"])
            assert len(result.results) == 1
            assert len(result.failed) == 1
            title, msg = result.failed[0]
            assert title == "BAD"
            assert "ValueError" in msg
            assert "测试失败" in msg

    def test_progress_callback(self):
        """进度回调被正确调用（顺序不保证，因为 as_completed）"""
        from mdifier import convert_many

        calls = []
        with patch("mdifier.lib.WikiFetcher") as MF, patch("mdifier.lib._convert_one") as CO:

            def mock_fetch(titles, **kwargs):
                return [_make_page(t) for t in titles]

            MF.return_value.fetch_many.side_effect = mock_fetch
            CO.side_effect = lambda c, p, t: _make_convert_result(t)

            def on_progress(done, total, title):
                calls.append((done, total, title))

            convert_many(["A", "B", "C"], on_progress=on_progress)

        # 3 次回调，done 范围 1-3
        assert len(calls) == 3
        done_values = sorted(c[0] for c in calls)
        assert done_values == [1, 2, 3]
        # total 总是 3
        assert all(c[1] == 3 for c in calls)
        # titles 包含 A/B/C
        titles = {c[2] for c in calls}
        assert titles == {"A", "B", "C"}

    def test_unresolved_collection(self):
        """_unresolved 被收集到 result.unresolved"""
        from mdifier import convert_many

        with (
            patch("mdifier.lib.WikiFetcher") as MF,
            patch("mdifier.lib._convert_one") as CO,
            patch("mdifier.lib.MarkdownConverter") as MC,
        ):

            def mock_fetch(titles, **kwargs):
                return [_make_page(t) for t in titles]

            MF.return_value.fetch_many.side_effect = mock_fetch
            CO.side_effect = lambda c, p, t: _make_convert_result(t)
            # 模拟 converter 实例的 _unresolved 集合
            MC.return_value._unresolved = {"test_template"}
            result = convert_many(["X"])
            assert "test_template" in result.unresolved


class TestConvertDetailed:
    def test_templates_are_populated(self):
        """convert_detailed 返回的 templates 非空"""
        from mdifier import convert_detailed

        with patch("mdifier.lib.WikiFetcher") as MF, patch("mdifier.lib.MarkdownConverter") as MC:
            MF.return_value.fetch.return_value = _make_page("铁锭")
            MC.return_value.convert_wiki.return_value = "# 铁锭\nbody"
            MC.return_value._template_cache = {"Hatnote": {"class": "hatnote", "text": "note"}}
            result = convert_detailed("铁锭")
            assert result.templates == {"Hatnote": {"class": "hatnote", "text": "note"}}
