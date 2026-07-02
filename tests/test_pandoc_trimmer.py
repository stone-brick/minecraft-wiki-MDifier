"""测试 pandoc_trimmer.py"""

from minecraft_wiki_mdifier.pandoc_trimmer import (
    FORMAT_RENDERERS,
    TEMPLATE_RENDERERS,
    _build_col_defs,
    _place_row_cells,
    _render_bv,
    _render_history_line,
    _render_history_table,
    _render_html_generic,
    _render_id_table,
    _render_navbox_items,
    _render_only,
    _render_table_grid,
    _render_template_table,
    _render_template_to_markdown,
    _strip_mediawiki_syntax,
    _wrap_template,
    wikitext_to_format,
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


# =============================================================================
# Step 1 — 核心函数测试
# =============================================================================


class TestBuildColDefs:
    """_build_col_defs 测试"""

    def test_single_row(self):
        """单行表头直接展开为列定义"""
        from bs4 import BeautifulSoup

        html = "<tr><th>A</th><th>B</th></tr>"
        soup = BeautifulSoup(html, "html.parser")
        header_trs = [soup.find_all("tr")[0].find_all("th")]
        col_defs = _build_col_defs(header_trs)
        assert [c["text"] for c in col_defs] == ["A", "B"]

    def test_multi_row_with_colspan(self):
        """colspan>1 展开为多个列定义"""
        from bs4 import BeautifulSoup

        html = (
            "<tr><th>A</th><th colspan='2'>B</th></tr><tr><th>A</th><th>Sub1</th><th>Sub2</th></tr>"
        )
        soup = BeautifulSoup(html, "html.parser")
        header_trs = [tr.find_all("th") for tr in soup.find_all("tr")]
        col_defs = _build_col_defs(header_trs)
        texts = [c["text"] for c in col_defs]
        assert texts == ["A(A)", "B(Sub1)", "B(Sub2)"]

    def test_multi_row_with_rowspan(self):
        """rowspan>1 只占 1 列"""
        from bs4 import BeautifulSoup

        html = "<tr><th rowspan='2'>A</th><th>B</th></tr><tr><th>Sub</th></tr>"
        soup = BeautifulSoup(html, "html.parser")
        header_trs = [tr.find_all("th") for tr in soup.find_all("tr")]
        col_defs = _build_col_defs(header_trs)
        # rowspan>1 的格子只作为 1 列
        assert len(col_defs) == 2

    def test_empty_sub_labels(self):
        """子行标签为空时只显示父标签"""
        from bs4 import BeautifulSoup

        html = "<tr><th>A</th><th>B</th></tr><tr><th></th><th></th></tr>"
        soup = BeautifulSoup(html, "html.parser")
        header_trs = [tr.find_all("th") for tr in soup.find_all("tr")]
        col_defs = _build_col_defs(header_trs)
        texts = [c["text"] for c in col_defs]
        assert texts == ["A", "B"]


class TestPlaceRowCells:
    """_place_row_cells 测试"""

    def test_rowspan_decrements_correctly(self):
        """rowspan=2 的格子在第 1 行设置后，第 2 行 col_state 应保留"""
        cells = [
            {"text": "A", "colspan": 1, "rowspan": 2},
            {"text": "B", "colspan": 1, "rowspan": 1},
        ]
        col_defs = [{"text": "Col1"}, {"text": "Col2"}]
        placed1, state1 = _place_row_cells(cells, col_defs, {})
        # 第 1 行：A 占 col0，B 占 col1
        assert placed1 == ["A", "B"]
        # remaining 从 1 递减为 0（>=1递减），col_state 仍保留 key 直到下轮彻底清除
        assert 0 in state1

    def test_colspan_spans_multiple_columns(self):
        """colspan=2 占两列位置"""
        cells = [
            {"text": "Wide", "colspan": 2, "rowspan": 1},
            {"text": "C", "colspan": 1, "rowspan": 1},
        ]
        col_defs = [{"text": "A"}, {"text": "B"}, {"text": "C"}]
        placed, _ = _place_row_cells(cells, col_defs, {})
        assert placed[0] == "Wide"
        assert placed[1] == ""
        assert placed[2] == "C"

    def test_col_state_skips_occupied(self):
        """col_state 占据的列应被跳过"""
        cells = [{"text": "B", "colspan": 1, "rowspan": 1}]
        col_defs = [{"text": "A"}, {"text": "B"}, {"text": "C"}]
        # col0 被 rowspan 占据
        col_state = {0: ("A", 1)}
        placed, _ = _place_row_cells(cells, col_defs, col_state)
        # B 应跳过 col0，放在 col1
        assert placed[1] == "B"

    def test_empty_row(self):
        """空行返回空列表，col_state 正确递减"""
        col_defs = [{"text": "A"}, {"text": "B"}]
        col_state = {0: ("A", 1), 1: ("B", 1)}
        placed, new_state = _place_row_cells([], col_defs, col_state)
        # 空行也应缩减 remaining
        assert all(v == 0 for _, v in new_state.values())


class TestRenderTableGrid:
    """_render_table_grid 测试"""

    def test_basic_table(self):
        """基本两列表格"""
        html = (
            "<table class='wikitable'>"
            "<tr><th>A</th><th>B</th></tr>"
            "<tr><td>1</td><td>2</td></tr>"
            "</table>"
        )
        result = _render_table_grid({"html": html}, "zh")
        assert "| A | B |" in result
        assert "| 1 | 2 |" in result

    def test_rowspan_vertical_span(self):
        """rowspan=2 垂直跨行"""
        html = (
            "<table class='wikitable'>"
            "<tr><th>生物</th><th>掉落物</th></tr>"
            "<tr><td rowspan='2'>僵尸</td><td>腐肉</td></tr>"
            "<tr><td>铁锭</td></tr>"
            "</table>"
        )
        result = _render_table_grid({"html": html}, "zh")
        lines = result.strip().split("\n")
        # 第 1 行数据
        assert "| 僵尸 | 腐肉 |" in lines[2]
        # 第 2 行：僵尸列为空（被 rowspan 占据），铁锭在第 2 列
        assert "|  | 铁锭 |" in lines[3] or "|  |  铁锭 |" in result

    def test_colspan_horizontal_span(self):
        """colspan=2 水平跨列"""
        html = (
            "<table class='wikitable'>"
            "<tr><th>A</th><th colspan='2'>BC</th></tr>"
            "<tr><th>A</th><th>B</th><th>C</th></tr>"
            "<tr><td>val</td><td>b</td><td>c</td></tr>"
            "</table>"
        )
        result = _render_table_grid({"html": html}, "zh")
        # colspan=2 的格子展开为 2 列
        lines = result.strip().split("\n")
        assert lines[0] == "| A(A) | BC(B) | BC(C) |"

    def test_complex_table_with_rowspan_and_colspan(self):
        """同时有 rowspan 和 colspan 的复杂表格"""
        html = (
            "<table class='wikitable'>"
            "<tr><th>物品</th><th>稀有度</th><th>数量</th></tr>"
            "<tr><td rowspan='2'>钻石</td><td>稀有</td><td>1-3</td></tr>"
            "<tr><td>史诗</td><td>1-2</td></tr>"
            "</table>"
        )
        result = _render_table_grid({"html": html}, "zh")
        lines = result.strip().split("\n")
        assert "| 钻石 | 稀有 | 1-3 |" in lines[2]
        assert "|  | 史诗 | 1-2 |" in lines[3]

    def test_empty_html_falls_back_to_text(self):
        """html 为空时回退到 text 字段"""
        result = _render_table_grid({"html": "", "text": "fallback text"}, "zh")
        assert "fallback text" in result

    def test_no_table_falls_back_to_generic(self):
        """无 table 标签时回退到 _render_html_generic"""
        html = "<div>not a table</div>"
        result = _render_table_grid({"html": html}, "zh")
        # generic 渲染器用 markdownify 处理，结果非空
        assert len(result) > 0


class TestRenderHtmlGeneric:
    """_render_html_generic 测试"""

    def test_basic_html_conversion(self):
        """HTML 转为 Markdown"""
        html = "<p>Hello <strong>World</strong></p>"
        result = _render_html_generic({"html": html}, "zh")
        assert "Hello" in result
        assert "World" in result

    def test_empty_html_falls_back_to_text(self):
        """html 为空时回退到 text"""
        result = _render_html_generic({"html": "", "text": "text only"}, "zh")
        assert "text only" in result

    def test_no_html_no_text_returns_empty(self):
        """html 和 text 都为空返回空字符串"""
        result = _render_html_generic({}, "zh")
        assert result == ""


class TestRenderTemplateToMarkdown:
    """_render_template_to_markdown 测试"""

    def test_dispatches_to_template_renderer(self):
        """模板名在 TEMPLATE_RENDERERS 中时使用对应渲染器"""
        expanded = {
            "html": "",
            "text": "bv content",
            "template_name": "bv",
        }
        result = _render_template_to_markdown(expanded, "zh")
        assert "bv" in result.lower()

    def test_dispatches_to_format_renderer(self):
        """format 在 FORMAT_RENDERERS 中时使用对应渲染器"""
        expanded = {
            "table": [["A", "B"], ["1", "2"]],
            "format": "table",
        }
        result = _render_template_to_markdown(expanded, "zh")
        assert "| A | B |" in result

    def test_no_match_falls_back_to_text(self):
        """无匹配时回退到 text"""
        expanded = {
            "html": "",
            "text": "plain fallback",
            "format": "unknown",
        }
        result = _render_template_to_markdown(expanded, "zh")
        assert "plain fallback" in result

    def test_wrap_template_name(self):
        """有 template_name 时用 _wrap_template 包裹"""
        expanded = {
            "table": [["A"], ["1"]],
            "format": "table",
            "template_name": "MyTable",
        }
        result = _render_template_to_markdown(expanded, "zh")
        assert ":::MyTable" in result


# =============================================================================
# Step 2 — wikitext_to_format 端到端测试
# =============================================================================


class TestWikitextToFormat:
    """wikitext_to_format 端到端测试"""

    def test_plain_text_preserved(self, expander_mock, monkeypatch):
        """无模板的纯文本直接返回"""
        import pypandoc

        monkeypatch.setattr(pypandoc, "convert_text", lambda text, *a, **kw: text)
        result = wikitext_to_format(
            wikitext="Plain text without templates",
            expander=expander_mock,
            page_title="Test",
            output_format="markdown",
            lang="zh",
        )
        assert "Plain text" in result

    def test_replaces_mediawiki_block(self, expander_mock, monkeypatch):
        """mediawiki 块被替换为渲染后的内容"""
        import pypandoc

        blocks = (
            chr(96) * 3 + "{=mediawiki}" + chr(10) + "{{Hatnote|example}}" + chr(10) + chr(96) * 3
        )
        monkeypatch.setattr(pypandoc, "convert_text", lambda text, *a, **kw: blocks)
        result = wikitext_to_format(
            wikitext="{{Hatnote|example}}",
            expander=expander_mock,
            page_title="Test",
            output_format="markdown",
            lang="zh",
        )
        assert "test" in result.lower()
        assert "{=mediawiki}" not in result

    def test_strips_mediawiki_residue(self, expander_mock, monkeypatch):
        """MediaWiki 残留语法被清理"""
        import pypandoc

        monkeypatch.setattr(
            pypandoc, "convert_text", lambda text, *a, **kw: "Some text {.wikilink}"
        )
        result = wikitext_to_format(
            wikitext="Some text {.wikilink}",
            expander=expander_mock,
            page_title="Test",
            output_format="markdown",
            lang="zh",
        )
        assert "{.wikilink}" not in result

    def test_inline_template_replaced(self, expander_mock, monkeypatch):
        """内联模板被正确替换"""
        import pypandoc

        # Pandoc 输出内联模板格式: `{{...}}`{=mediawiki}
        inline = "`{{Hatnote|inline}}`{=mediawiki}"
        monkeypatch.setattr(pypandoc, "convert_text", lambda text, *a, **kw: inline)
        result = wikitext_to_format(
            wikitext="{{Hatnote|inline}}",
            expander=expander_mock,
            page_title="Test",
            output_format="markdown",
            lang="zh",
        )
        assert "test" in result.lower()

    def test_unknown_template_preserved(self, expander_mock, monkeypatch):
        """未知模板保持原样（不崩溃）"""
        import pypandoc

        def fake_expand(content, page_title):
            return {"text": "[[:Template:Unknown]]", "html": "", "class": ""}

        block = chr(96) * 3 + "{=mediawiki}" + chr(10) + "{{Unknown|arg}}" + chr(10) + chr(96) * 3
        monkeypatch.setattr(pypandoc, "convert_text", lambda text, *a, **kw: block)
        expander_mock.expand.side_effect = fake_expand
        result = wikitext_to_format(
            wikitext="{{Unknown|arg}}",
            expander=expander_mock,
            page_title="Test",
            output_format="markdown",
            lang="zh",
        )
        assert "Unknown" in result
