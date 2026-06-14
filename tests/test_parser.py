"""测试 WikiParser"""

from mdifier.parser import NodeType, WikiParser


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
