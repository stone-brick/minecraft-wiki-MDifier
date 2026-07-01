"""测试 pandoc_trimmer.py"""

from minecraft_wiki_mdifier.pandoc_trimmer import (
    FORMAT_RENDERERS,
    TEMPLATE_RENDERERS,
    _render_bv,
    _render_history_line,
    _render_history_table,
    _render_id_table,
    _render_navbox_items,
    _render_only,
    _render_template_table,
    _strip_mediawiki_syntax,
    _wrap_template,
)


class TestWrapTemplate:
    """_wrap_template 测试"""

    def test_wrap_with_name(self):
        result = _wrap_template("TestTemplate", "content")
        assert result == ":::TestTemplate\ncontent\n:::\n"

    def test_wrap_without_name(self):
        result = _wrap_template(None, "content")
        assert result == "content"


class TestStripMediawikiSyntax:
    """_strip_mediawiki_syntax 测试"""

    def test_strip_wikilink_attributes(self):
        text = "some text {.wikilink} more {#idname} text"
        result = _strip_mediawiki_syntax(text)
        assert "{#" not in result
        assert "{." not in result

    def test_strip_title_attributes(self):
        text = '![alt](url "title")'
        result = _strip_mediawiki_syntax(text)
        assert '"title"' not in result

    def test_strip_file_category_links(self):
        text = "[[File:Image.png]] and [[Category:Test]]"
        result = _strip_mediawiki_syntax(text)
        assert "File:" not in result
        assert "Category:" not in result

    def test_strip_pipe_links(self):
        text = "[[Page|text]]"
        result = _strip_mediawiki_syntax(text)
        assert result == "[text](Page)"

    def test_strip_empty_links(self):
        text = "![](/)"
        result = _strip_mediawiki_syntax(text)
        assert "!(" not in result


class TestRenderTemplateTable:
    """_render_template_table 测试"""

    def test_render_table_basic(self):
        info = {
            "table": [["A", "B"], ["1", "2"]],
            "template_name": "TestTable",
            "class": "wikitable",
        }
        result = _render_template_table(info, "zh")
        assert ":::TestTable" in result
        assert "| A | B |" in result
        assert "| 1 | 2 |" in result
        assert "| --- |" in result

    def test_render_table_with_newlines(self):
        """换行符应转为 <br/>"""
        info = {
            "table": [["A\nB", "C"]],
            "template_name": "Test",
            "class": "table",
        }
        result = _render_template_table(info, "zh")
        assert "<br/>" in result

    def test_render_table_empty_falls_back_to_text(self):
        info = {"table": [], "text": "No data"}
        result = _render_template_table(info, "zh")
        assert "No data" in result


class TestRenderHistoryLine:
    """_render_history_line 测试"""

    def test_render_history_line_with_html(self):
        info = {
            "html": "<tr><th>1.0.0</th><td>Added feature</td></tr>",
            "text": "",
        }
        result = _render_history_line(info, "zh")
        assert "**1.0.0**" in result
        assert "Added feature" in result
        assert ":::HistoryLine" in result

    def test_render_history_line_fallback_to_text(self):
        info = {"html": "", "text": "Some text"}
        result = _render_history_line(info, "zh")
        assert "Some text" in result


class TestRenderHistoryTable:
    """_render_history_table 测试"""

    def test_render_history_table_with_html(self):
        info = {
            "html": """
            <table>
                <tr><th colspan="6">Java版</th></tr>
                <tr><th>1.0.0</th><td colspan="4"></td><td>Added feature</td></tr>
            </table>
            """,
        }
        result = _render_history_table(info, "zh")
        assert ":::HistoryTable" in result
        assert "Java版" in result
        assert "**1.0.0**" in result
        assert "Added feature" in result

    def test_render_history_table_empty(self):
        info = {"html": ""}
        result = _render_history_table(info, "zh")
        assert ":::HistoryTable" in result


class TestRenderOnly:
    """_render_only 测试"""

    def test_render_only_basic(self):
        info = {
            "params": {"1": "Java版", "2": "仅在 Java版 可用"},
            "text": "",
        }
        result = _render_only(info, "zh")
        assert ":::Only" in result
        assert "Java版" in result


class TestRenderIdTable:
    """_render_id_table 测试"""

    def test_render_id_table_with_table(self):
        info = {
            "table": [
                ["名称", "命名空间ID"],
                ["Iron Ingot", "iron_ingot"],
            ],
            "template_name": "ID table",
        }
        result = _render_id_table(info, "zh")
        assert ":::ID table" in result
        assert "| 名称 |" in result
        assert "| Iron Ingot |" in result

    def test_render_id_table_empty(self):
        info = {"table": [], "text": "No data"}
        result = _render_id_table(info, "zh")
        assert "No data" in result


class TestRenderNavboxItems:
    """_render_navbox_items 测试"""

    def test_render_navbox_items_extracts_items(self):
        info = {
            "html": "<ul><li>Item1</li><li>Item2</li></ul>",
            "text": "",
        }
        result = _render_navbox_items(info, "zh")
        assert ":::Navbox items" in result
        assert "Item1" in result
        assert "Item2" in result

    def test_render_navbox_items_empty(self):
        info = {"html": "", "text": "No navbox"}
        result = _render_navbox_items(info, "zh")
        assert "No navbox" in result


class TestRenderBv:
    """_render_bv 测试"""

    def test_render_bv_extracts_iframe_src(self):
        info = {
            "html": """
            <figure>
                <iframe class="embedvideo-player" src="//player.bilibili.com/player.html?bvid=BV123456"></iframe>
            </figure>
            """,
            "text": "",
        }
        result = _render_bv(info, "zh")
        assert ":::bv" in result
        assert "player.bilibili.com" in result
        assert "BV123456" in result

    def test_render_bv_empty(self):
        info = {"html": "", "text": "No video"}
        result = _render_bv(info, "zh")
        assert "No video" in result


class TestTemplateRenderersRegistry:
    """TEMPLATE_RENDERERS 注册表测试"""

    def test_historyline_has_renderer(self):
        assert "historyline" in TEMPLATE_RENDERERS

    def test_historytable_has_renderer(self):
        assert "historytable" in TEMPLATE_RENDERERS

    def test_id_table_has_renderer(self):
        assert "id table" in TEMPLATE_RENDERERS

    def test_navbox_items_has_renderer(self):
        assert "navbox items" in TEMPLATE_RENDERERS

    def test_bv_has_renderer(self):
        assert "bv" in TEMPLATE_RENDERERS


class TestFormatRenderersRegistry:
    """FORMAT_RENDERERS 注册表测试"""

    def test_table_has_renderer(self):
        assert "table" in FORMAT_RENDERERS

    def test_infobox_table_has_renderer(self):
        assert "infobox_table" in FORMAT_RENDERERS

    def test_mcui_has_renderer(self):
        assert "mcui" in FORMAT_RENDERERS
