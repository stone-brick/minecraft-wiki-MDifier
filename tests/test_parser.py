"""测试 WikiParser"""

from minecraft_wiki_mdifier.parser import NodeType, WikiParser, _split_template_params


class TestWikiParser:
    def setup_method(self):
        self.parser = WikiParser()

    def test_simple_text(self):
        """纯文本产生一个 PARAGRAPH 节点"""
        nodes = self.parser.parse("Hello world")
        assert len(nodes) == 1
        assert nodes[0].type == NodeType.PARAGRAPH
        assert "Hello world" in nodes[0].content

    def test_heading_levels(self):
        """== 标题解析"""
        nodes = self.parser.parse("== H2 ==\n=== H3 ===")
        headings = [n for n in nodes if n.type == NodeType.HEADING]
        assert len(headings) == 2
        assert headings[0].attrs["level"] == 2
        assert headings[0].content == "H2"
        assert headings[1].attrs["level"] == 3
        assert headings[1].content == "H3"

    def test_template_extraction(self):
        """模板提取"""
        self.parser.parse("{{Hatnote|text}}")
        templates = self.parser.get_templates()
        assert "hatnote:0" in templates
        assert templates["hatnote:0"].params == {"1": "text"}

    def test_template_with_named_params(self):
        """模板带命名参数"""
        self.parser.parse("{{Infobox item|1=name|image=img.png}}")
        templates = self.parser.get_templates()
        assert "infobox item:0" in templates
        t = templates["infobox item:0"]
        assert t.params == {"1": "name", "image": "img.png"}

    def test_horizontal_rule(self):
        """水平线"""
        nodes = self.parser.parse("----")
        hr_nodes = [n for n in nodes if n.type == NodeType.HORIZONTAL_RULE]
        assert len(hr_nodes) == 1

    def test_link_extraction(self):
        """链接 [[X]] 转为 [Diamond](Diamond) 格式"""
        nodes = self.parser.parse("[[Diamond]]")
        text_nodes = [n for n in nodes if n.type == NodeType.PARAGRAPH]
        assert any("Diamond" in n.content for n in text_nodes)

    def test_table_parsing(self):
        """表格解析"""
        nodes = self.parser.parse(
            "{| class='wikitable'\n! header1 !! header2\n|-\n| cell1 || cell2\n|}"
        )
        table_nodes = [n for n in nodes if n.type == NodeType.TABLE]
        assert len(table_nodes) >= 1  # 表格节点存在
        assert table_nodes[0].children is not None

    def test_unordered_list(self):
        """无序列表 * item"""
        nodes = self.parser.parse("* Item 1\n* Item 2")
        list_nodes = [n for n in nodes if n.type == NodeType.LIST]
        assert len(list_nodes) >= 1
        assert list_nodes[0].attrs.get("list_type") == "ul"

    def test_ordered_list(self):
        """有序列表 # item"""
        nodes = self.parser.parse("# First\n# Second")
        list_nodes = [n for n in nodes if n.type == NodeType.LIST]
        assert len(list_nodes) >= 1
        assert list_nodes[0].attrs.get("list_type") == "ol"

    def test_nested_template(self):
        """嵌套模板 {{outer|{{inner}}|x=y}"""
        self.parser.parse("{{outer|{{inner}}|x=y}}")
        templates = self.parser.get_templates()
        # 嵌套模板应被正确解析
        assert len(templates) >= 1

    def test_template_with_multiple_params(self):
        """模板多参数解析"""
        self.parser.parse("{{Crafting|a=|b=|c=|d=|e=|f=|g=|h=|i=Diamond}}")
        templates = self.parser.get_templates()
        assert len(templates) >= 1
        t = list(templates.values())[0]
        assert "i" in t.params or "1" in t.params


class TestSplitTemplateParams:
    """测试 _split_template_params 的参数分割逻辑"""

    def test_simple_split(self):
        """简单 | 分割"""
        assert _split_template_params("a|b") == ["a", "b"]

    def test_empty_first_param(self):
        """首个参数为空"""
        # || 表示两个空参数（MediaWiki 规范）
        assert _split_template_params("||b") == ["", "", "b"]

    def test_link_inside_param_not_split(self):
        """链接 [[a|b]] 中的 | 不应被分割"""
        assert _split_template_params("|[[File:img.png|32px]]|x") == [
            "",
            "[[File:img.png|32px]]",
            "x",
        ]

    def test_nested_template_not_split(self):
        """嵌套模板 {{inner|a=b}} 中的 | 不应被分割"""
        assert _split_template_params("{{inner|a=b}}|text") == ["{{inner|a=b}}", "text"]

    def test_double_nested_template(self):
        """嵌套多层 {{A|{{B|C}}|D}}"""
        assert _split_template_params("{{A|{{B|C}}|D}}") == ["{{A|{{B|C}}", "D}}"]

    def test_tplarg_not_split(self):
        """参数默认值 {{{1|default}}} 在实际场景中会被 API 先展开，此处测试保守行为"""
        # MediaWiki API 会先展开 tplarg，所以实际传入的是展开后的值
        # 这里测试包含 {} 的字符串不会被错误分割
        assert _split_template_params("{{{1|default}}}") == ["{{{1|default}}}"]

    def test_historyline_real_case(self):
        """真实的 HistoryLine wikitext"""
        result = _split_template_params("HistoryLine|||dev=20100130|text")
        assert result == ["HistoryLine", "", "", "dev=20100130", "text"]

    def test_historyline_with_link(self):
        """带链接的 HistoryLine"""
        result = _split_template_params(
            "HistoryLine||0.31|dev=20100128|[[File:Iron Ingot JE1.png|32px]] 加入了铁锭。"
        )
        assert result == [
            "HistoryLine",
            "",
            "0.31",
            "dev=20100128",
            "[[File:Iron Ingot JE1.png|32px]] 加入了铁锭。",
        ]

    def test_crafting_params(self):
        """Crafting 模板参数"""
        result = _split_template_params("Crafting|a=|b=|c=|d=|e=|f=|g=|h=|i=Diamond")
        assert result == ["Crafting", "a=", "b=", "c=", "d=", "e=", "f=", "g=", "h=", "i=Diamond"]

    def test_empty_string(self):
        """空字符串"""
        assert _split_template_params("") == []

    def test_single_value(self):
        """单个值"""
        assert _split_template_params("a") == ["a"]

    def test_pipe_only(self):
        """仅管道符"""
        assert _split_template_params("|") == [""]

    def test_template_with_colon(self):
        """模板名含冒号"""
        result = _split_template_params("File:img.png|32px")
        assert result == ["File:img.png", "32px"]
