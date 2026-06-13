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
        """_fallback_template 返回 {name: k=v} 形式"""
        result = self.c._fallback_template("Hatnote", {"1": "text"})
        assert result["class"] is None
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
        assert "<template:hatnote start>" in result
        assert "x" in result
        assert "before" in result
        assert "after" in result
