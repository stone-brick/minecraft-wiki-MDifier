"""测试 MarkdownConverter 纯逻辑（不调用 expander）"""

from unittest.mock import MagicMock

from minecraft_wiki_mdifier.converter import MarkdownConverter
from minecraft_wiki_mdifier.parser import Node, NodeType


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


class TestExpandTemplateLogging:
    """_expand_template 异常时日志记录测试"""

    def test_expand_template_logs_on_expander_error(self, caplog):
        """expander.expand 失败时记录 debug 日志"""
        import logging

        c = MarkdownConverter(lang="zh", use_persistent_cache=False)
        c.expander = MagicMock()
        c.expander.expand.side_effect = RuntimeError("API error")

        with caplog.at_level(logging.DEBUG, "minecraft_wiki_mdifier.converter"):
            result = c._expand_template("Hatnote", {"1": "text"}, page_title="Test page")

        # 应该返回 fallback 结果
        assert result["class"] == "error"
        # 应该记录日志
        assert any("Hatnote" in msg and "API error" in msg for msg in caplog.messages)


class TestExpandAllTemplatesLogging:
    """_expand_all_templates 异常时日志记录测试"""

    def test_expand_all_templates_continues_on_single_error(self, caplog):
        """单个模板失败时记录日志但不中断其他模板"""
        import logging

        c = MarkdownConverter(lang="zh", use_persistent_cache=False)

        # mock expander.expand，前两次成功，第三次抛出异常
        call_count = [0]

        def mock_expand(template_call, page_title=None):
            call_count[0] += 1
            if call_count[0] >= 3:
                raise RuntimeError("expand failed")
            return {
                "html": "<div>ok</div>",
                "class": "hatnote",
                "text": "ok",
                "format": "text",
                "table": None,
                "template_name": "test",
            }

        c.expander = MagicMock()
        c.expander.expand = mock_expand

        from minecraft_wiki_mdifier.parser import TemplateInfo

        templates = {
            "t1": TemplateInfo(name="T1", params={"1": "a"}),
            "t2": TemplateInfo(name="T2", params={"1": "b"}),
            "t3": TemplateInfo(name="T3", params={"1": "c"}),
        }

        with caplog.at_level(logging.DEBUG, "minecraft_wiki_mdifier.converter"):
            result = c._expand_all_templates(templates)

        # 三个模板都应该有结果（失败的走 fallback）
        assert "t1" in result
        assert "t2" in result
        assert "t3" in result
        # t1, t2 成功，t3 走 fallback
        assert result["t1"]["class"] == "hatnote"
        assert result["t2"]["class"] == "hatnote"
        assert result["t3"]["class"] == "error"  # fallback
        # 应该记录了 t3 的错误日志（Template t3）
        assert any("t3" in msg and "expand failed" in msg for msg in caplog.messages)


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


class TestEncodeCacheValue:
    """_encode_cache_value 测试"""

    def test_encode_never_contains_pipe(self):
        """base64 编码结果中不包含 |，避免分隔符冲突"""
        from minecraft_wiki_mdifier.converter import _encode_cache_value

        # 包含各种特殊字符的值
        test_values = [
            "a|b",
            "x|y|z",
            "key=value",
            "a|b=c|d",
            "{}|[]",
            "中文|english",
        ]
        for v in test_values:
            encoded = _encode_cache_value(v)
            # URL-safe base64 不包含 |，确保分隔符不冲突
            assert "|" not in encoded, f"encoded value should not contain pipe: {encoded}"

    def test_encode_decode_roundtrip(self):
        """编码后能正确还原"""
        from minecraft_wiki_mdifier.converter import _encode_cache_value

        test_values = [
            "simple",
            "a|b|c",
            "key=value",
            "mixed|a=b|normal",
            "123|456|789",
        ]
        for v in test_values:
            # 由于使用 base64，编码后直接解码应该能还原
            import base64

            encoded = _encode_cache_value(v)
            decoded = base64.urlsafe_b64decode(encoded).decode("utf-8")
            assert decoded == v


class TestCancelThreadSafety:
    """cancel() 和 is_cancelled() 线程安全测试"""

    def test_cancel_is_thread_safe(self):
        """cancel() 从多线程并发调用时无数据竞争"""
        import threading

        converter = MarkdownConverter(lang="zh", use_persistent_cache=False)
        converter._cancelled = False  # 重置状态

        call_count = {"cancel": 0, "check": 0}
        results = []

        def cancel_repeatedly():
            for _ in range(100):
                converter.cancel()
                call_count["cancel"] += 1

        def check_cancelled_repeatedly():
            for _ in range(100):
                results.append(converter.is_cancelled())
                call_count["check"] += 1

        threads = [
            threading.Thread(target=cancel_repeatedly),
            threading.Thread(target=cancel_repeatedly),
            threading.Thread(target=check_cancelled_repeatedly),
            threading.Thread(target=check_cancelled_repeatedly),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证 is_cancelled() 至少被调用了预期次数
        assert call_count["check"] == 200
        # cancel 被调用至少一次后，is_cancelled 应该返回 True
        assert converter.is_cancelled() is True
