"""测试 MarkdownConverter 纯逻辑（不调用 expander）"""

from unittest.mock import MagicMock

from mdifier.converter import MarkdownConverter
from mdifier.parser import Node, NodeType


class TestMarkdownConverter:
    def setup_method(self):
        """构造 converter，用 mock expander 避免网络"""
        self.c = MarkdownConverter(lang="zh", use_persistent_cache=False)
        # expander 已被 MarkdownConverter 创建为 TemplateExpander 实例
        # 用 mock 替换 expand
        self.c.expander = MagicMock()

    def test_init_use_persistent_cache_false(self):
        """use_persistent_cache=False 走空缓存"""
        c = MarkdownConverter(lang="zh", use_persistent_cache=False)
        assert c._template_cache == {}
        assert c.max_workers == 10

    def test_init_default_uses_persistent(self):
        """默认 use_persistent_cache=True"""
        c = MarkdownConverter(lang="zh")
        # 不校验具体缓存内容（依赖磁盘），仅校验不为空或 None
        assert c._template_cache is not None

    def test_resolve_template_name_manual(self):
        """手工驼峰映射优先"""
        result = self.c._resolve_template_name("lootchestitem")
        assert result == "LootChestItem"

    def test_resolve_template_name_pascal_fallback(self):
        """未映射时自动尝试 PascalCase"""
        result = self.c._resolve_template_name("for")
        assert result == "For"
        # id_table 含下划线（isalpha=False），不自动转
        result = self.c._resolve_template_name("id_table")
        assert result == "id_table"

    def test_resolve_template_name_no_change(self):
        """已大写或非全小写不自动转"""
        result = self.c._resolve_template_name("Already_Capitalized")
        assert result == "Already_Capitalized"

    def test_fallback_template(self):
        """_fallback_template 返回 {name: k=v} 形式，class="error" 标记展开失败"""
        result = self.c._fallback_template("Hatnote", {"1": "text"})
        assert result["class"] == "error"
        assert result["format"] == "text"
        assert "[Hatnote: 1=text]" in result["text"]

    def test_render_heading_level_limit(self):
        """heading level 限制 ≤ 6"""
        node = Node(type=NodeType.HEADING, content="Title", attrs={"level": 10})
        result = self.c._render_heading(node)
        assert result == "###### Title\n"

    def test_render_horizontal_rule(self):
        """水平线"""
        node = Node(type=NodeType.HORIZONTAL_RULE, content="")
        result = self.c._render_horizontal_rule(node)
        assert result == "---\n"

    def test_render_table_with_empty_children(self):
        """空 children 表格返回空"""
        node = Node(type=NodeType.TABLE, content="", attrs={})
        assert self.c._render_table(node) == ""

    def test_replace_template_placeholders_missing(self):
        """缺失的模板保留原 token"""
        text = "{TEMPLATE:nonexistent}"
        result = self.c._replace_template_placeholders(text, {})
        assert result == "{TEMPLATE:nonexistent}"

    def test_replace_template_placeholders_substitute(self):
        """找到的模板被替换"""
        # 直接构造 expanded_templates（key 小写）
        expanded = {
            "hatnote": {
                "html": "<div>x</div>",
                "class": "hatnote",
                "text": "x",
                "format": "text",
                "table": None,
            }
        }
        text = "before {TEMPLATE:hatnote} after"
        result = self.c._replace_template_placeholders(text, expanded)
        assert ":::hatnote" in result
        assert "x" in result
        assert "before" in result
        assert "after" in result


class TestRenderTemplateTable:
    """_render_template_table 测试"""

    def setup_method(self):
        """构造 converter，用 mock expander 避免网络"""
        self.c = MarkdownConverter(lang="zh", use_persistent_cache=False)
        self.c.expander = MagicMock()

    def test_render_table_with_infobox_data(self):
        """infobox 表格数据渲染为 Markdown"""
        template_data = {
            "table": [
                ["Label 1", "Value 1"],
                ["Label 2", "Value 2"],
            ],
            "template_name": "infobox item",
            "class": "infobox",
        }
        result = self.c._render_template_table(template_data)
        assert ":::infobox item" in result
        assert "| Label 1 |" in result
        assert "| Value 1 |" in result
        assert "| --- |" in result  # 表头分隔行

    def test_render_table_with_mcui_data(self):
        """mcui 配方格式渲染为 3x3 网格"""
        template_data = {
            "table": [
                ["A", "B", "C"],
                ["D", "E", "F"],
                ["G", "H", "I"],
            ],
            "template_name": "Crafting",
            "class": "mcui",
        }
        result = self.c._render_template_table(template_data)
        assert ":::Crafting" in result
        assert "| A | B | C |" in result
        assert "| D | E | F |" in result

    def test_render_table_empty_falls_back_to_text(self):
        """table 为空时回退到 text"""
        template_data = {
            "table": [],
            "text": "No table data",
            "class": "hatnote",
        }
        result = self.c._render_template_table(template_data)
        assert "No table data" in result

    def test_render_table_with_trade_data(self):
        """Trade uses 表格数据（多列）"""
        template_data = {
            "table": [
                ["Villager", "Level", "Wanted", "Receives"],
                ["Armorer", "Apprentice", "4× Iron Ingot", "Emerald"],
                ["Weaponsmith", "Journeyman", "3× Iron Ingot", "Emerald"],
            ],
            "template_name": "Trade uses",
            "class": "trade_uses",
        }
        result = self.c._render_template_table(template_data)
        assert ":::Trade uses" in result
        assert "| Armorer |" in result
        assert "| Apprentice |" in result
        assert "| 4× Iron Ingot |" in result

    def test_render_table_without_template_name(self):
        """无 template_name 时只输出表格内容"""
        template_data = {
            "table": [["A", "B"]],
            "class": None,
        }
        result = self.c._render_template_table(template_data)
        assert "| A | B |" in result
        assert ":::" not in result


class TestRenderParagraph:
    """_render_paragraph 测试"""

    def setup_method(self):
        self.c = MarkdownConverter(lang="zh", use_persistent_cache=False)
        self.c.expander = MagicMock()

    def test_render_paragraph_with_links(self):
        """段落中的链接被正确渲染"""
        node = Node(
            type=NodeType.PARAGRAPH,
            content="see [[Diamond]] for details",
            attrs={},
        )
        # WikiParser 会将 [[Diamond]] 转换为 [Diamond](页面链接)
        # 替换后的内容应该是转换后的 Markdown 链接格式
        result = self.c._render_paragraph(node, {})
        assert "see" in result
        assert "details" in result

    def test_render_paragraph_with_template_placeholder(self):
        """段落中的模板占位符被替换"""
        node = Node(
            type=NodeType.PARAGRAPH,
            content="note: {TEMPLATE:hatnote}",
            attrs={},
        )
        expanded = {
            "hatnote": {
                "html": "<div>important note</div>",
                "class": "hatnote",
                "text": "important note",
                "format": "text",
                "table": None,
            }
        }
        result = self.c._render_paragraph(node, expanded)
        assert "important note" in result


class TestRenderList:
    """_render_list 测试"""

    def setup_method(self):
        self.c = MarkdownConverter(lang="zh", use_persistent_cache=False)
        self.c.expander = MagicMock()

    def test_render_unordered_list(self):
        """无序列表"""
        node = Node(type=NodeType.LIST, content="", attrs={"list_type": "ul"})
        child = Node(type=NodeType.LIST_ITEM, content="Item 1", attrs={})
        node.children.append(child)
        child2 = Node(type=NodeType.LIST_ITEM, content="Item 2", attrs={})
        node.children.append(child2)

        result = self.c._render_list(node, {})
        assert "- Item 1" in result
        assert "- Item 2" in result

    def test_render_ordered_list(self):
        """有序列表"""
        node = Node(type=NodeType.LIST, content="", attrs={"list_type": "ol"})
        child = Node(type=NodeType.LIST_ITEM, content="First", attrs={})
        node.children.append(child)

        result = self.c._render_list(node, {})
        assert "1. First" in result
