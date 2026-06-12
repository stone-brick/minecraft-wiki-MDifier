"""
Markdown转换器

将解析后的AST转换为Markdown格式
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from markdownify import markdownify as md

from mdifier.parser import Node, NodeType, TemplateInfo, WikiParser
from mdifier.template_expander import TemplateExpander
from mdifier.wiki import WikiPage

# 节点类型 → 渲染方法名（注册表）
NODE_RENDERERS: dict[NodeType, str] = {
    NodeType.HEADING: "_render_heading",
    NodeType.PARAGRAPH: "_render_paragraph",
    NodeType.LIST: "_render_list",
    NodeType.TABLE: "_render_table",  # AST 节点 table
    NodeType.HORIZONTAL_RULE: "_render_horizontal_rule",
    NodeType.TEXT: "_render_text",
}

# 需要 expanded_templates 参数的渲染器
_NODE_RENDERERS_NEED_TEMPLATES = {
    "_render_paragraph",
    "_render_list",
    "_render_text",
}


class MarkdownConverter:
    """Markdown转换器"""

    # 格式渲染器映射：format → 方法名
    FORMAT_RENDERERS = {
        "infobox_table": "_render_template_table",
        "table": "_render_template_table",
        "mcui": "_render_template_table",
    }

    # 已知需要驼峰转写的模板名（小写 -> 正确名）
    # parser 提取时统一小写，但 MediaWiki 区分大小写
    CAMEL_CASE_TEMPLATES = {
        "lootchestitem": "LootChestItem",
        "archaeologylootitem": "ArchaeologyLootItem",
        "itemlink": "ItemLink",
        "craftingtable": "CraftingTable",
        "droptable": "Droptable",
        "lootchest": "LootChest",
        "historytable": "HistoryTable",
        "historyline": "HistoryLine",
        "ilink": "ILink",
        "columns-list": "Columns-list",
        "columns list": "Columns-list",
        "edition": "Edition",
        "id table": "ID table",
        "crafting usage": "Crafting usage",
        "trade uses": "Trade uses",
        "drop sources": "Drop sources",
        "navbox items": "Navbox items",
        "video note": "Video note",
        "sound table/block/stone": "Sound table/block/stone",
    }

    def __init__(
        self,
        lang: str = "zh",
        max_workers: int = 10,
        template_cache: dict | None = None,
    ):
        self.parser = WikiParser()
        self.expander = TemplateExpander(lang=lang)
        self.max_workers = max_workers
        # 跨页共享的模板缓存（外部注入实现多批次共享）
        self._template_cache = template_cache if template_cache is not None else {}
        self._cache_lock = threading.Lock()

    def convert_wiki(self, page: WikiPage) -> str:
        """
        转换Wiki页面为Markdown

        Args:
            page: WikiPage对象

        Returns:
            Markdown格式字符串
        """
        return self._convert_wikitext(page.content, page.title)

    def _convert_wikitext(self, wikitext: str, title: str) -> str:
        """
        将WikiText转换为Markdown

        Args:
            wikitext: WikiText内容
            title: 页面标题

        Returns:
            Markdown格式字符串
        """
        # 阶段1:解析AST
        nodes = self.parser.parse(wikitext)

        # 阶段2: 提取模板
        templates = self.parser.get_templates()

        # 阶段3: 展开模板
        expanded_templates = self._expand_all_templates(templates)

        # 阶段4: 生成Markdown
        return self._generate_markdown(nodes, expanded_templates, title)

    def _expand_all_templates(self, templates: dict[str, TemplateInfo]) -> dict[str, dict]:
        """
        并发展开所有模板（10x 加速）

        Args:
            templates: 模板字典

        Returns:
            展开后的模板字典
        """
        expanded = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_name = {
                executor.submit(
                    self._expand_template, info.name, info.params
                ): name
                for name, info in templates.items()
            }

            # 收集结果
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    expanded[name] = future.result()
                except Exception:
                    # 单个模板失败不应中断整体
                    expanded[name] = self._fallback_template(
                        name, templates[name].params
                    )

        return expanded

    def _expand_template(self, name: str, params: dict[str, str]) -> dict:
        """
        展开单个模板（带跨页缓存）

        Args:
            name: 模板名称
            params: 模板参数

        Returns:
            展开结果 dict
        """
        # 构建缓存键：模板名 + 完整参数（不同物品的同模板结果不同）
        api_name = self.CAMEL_CASE_TEMPLATES.get(name.lower(), name)
        parts = [api_name]
        for key, value in params.items():
            if key.isdigit():
                parts.append(value)
            else:
                parts.append(f"{key}={value}")
        cache_key = "|".join(parts)

        # 缓存命中
        with self._cache_lock:
            if cache_key in self._template_cache:
                return self._template_cache[cache_key]

        # 缓存未命中 → 实际调用
        template_call = "{{" + cache_key + "}}"
        try:
            expanded = self.expander.expand(template_call)
            result = {
                "name": name,
                "class": expanded["class"],
                "text": expanded["text"],
                "html": expanded["html"],
                "format": expanded.get("format", "text"),
                "table": expanded.get("table")
            }
        except Exception:
            result = self._fallback_template(name, params)

        with self._cache_lock:
            self._template_cache[cache_key] = result
        return result

    def _fallback_template(self, name: str, params: dict[str, str]) -> dict:
        """
        模板展开失败时的回退结果

        Args:
            name: 模板名称
            params: 模板参数

        Returns:
            回退 dict
        """
        params_str = ", ".join(f"{k}={v}" for k, v in params.items())
        return {
            "name": name,
            "class": None,
            "text": f"[{name}: {params_str}]",
            "html": None,
            "format": "text",
            "table": None
            }

    def _generate_markdown(
        self,
        nodes: list[Node],
        expanded_templates: dict[str, dict],
        title: str
    ) -> str:
        """
        生成Markdown

        Args:
            nodes: AST节点列表
            expanded_templates: 展开后的模板字典
            title: 页面标题

        Returns:
            Markdown格式字符串
        """
        lines = [f'# {title}', '']

        for node in nodes:
            lines.append(self._render_node(node, expanded_templates))

        return '\n'.join(lines)

    def _render_node(self, node: Node, expanded_templates: dict[str, dict]) -> str:
        """
        渲染单个节点

        Args:
            node: AST节点
            expanded_templates: 展开后的模板字典

        Returns:
            Markdown字符串
        """
        renderer_name = NODE_RENDERERS.get(node.type)
        if not renderer_name:
            return ''
        renderer = getattr(self, renderer_name)
        # 根据渲染器签名决定是否传 expanded_templates
        if renderer_name in _NODE_RENDERERS_NEED_TEMPLATES:
            return renderer(node, expanded_templates)
        return renderer(node)

    def _render_horizontal_rule(self, node: Node) -> str:
        """水平线"""
        return '---\n'

    def _render_heading(self, node: Node) -> str:
        """渲染标题节点"""
        level = min(node.attrs.get('level', 2), 6)
        return f'{"#" * level} {node.content}\n'

    def _render_paragraph(self, node: Node, expanded_templates: dict[str, dict]) -> str:
        """渲染段落节点"""
        content = self._replace_template_placeholders(node.content, expanded_templates)
        return f'{content}\n'

    def _render_list(self, node: Node, expanded_templates: dict[str, dict]) -> str:
        """渲染列表节点"""
        lines = []
        list_type = node.attrs.get('list_type', 'ul')
        marker = '- ' if list_type == 'ul' else '1. '
        for item in node.children:
            if item.type == NodeType.LIST_ITEM:
                content = self._replace_template_placeholders(item.content, expanded_templates)
                lines.append(f'{marker}{content}')
        lines.append('')
        return '\n'.join(lines)

    def _render_table(self, node: Node) -> str:
        """渲染表格节点"""
        if not node.children:
            return ''
        lines = ['| ' + ' | '.join(c.content for c in node.children) + ' |']
        lines.append('| ' + ' | '.join(['---'] * len(node.children)) + ' |')
        lines.append('')
        return '\n'.join(lines)

    def _render_text(self, node: Node, expanded_templates: dict[str, dict]) -> str:
        """渲染文本节点"""
        return self._replace_template_placeholders(node.content, expanded_templates)

    def _replace_template_placeholders(
        self,
        text: str,
        expanded_templates: dict[str, dict]
    ) -> str:
        """
        替换文本中的模板占位符

        Args:
            text: 文本内容
            expanded_templates: 展开后的模板字典

        Returns:
            替换后的文本
        """
        import re
        pattern = re.compile(r'\{TEMPLATE:([^{}]+?)\}')

        def replace_match(match):
            template_name = match.group(1).lower()
            info = expanded_templates.get(template_name)
            if not info:
                return match.group(0)

            fmt = info.get("format", "text")

            # 通过 FORMAT_RENDERERS 查找渲染方法
            renderer_name = self.FORMAT_RENDERERS.get(fmt)
            if renderer_name:
                return getattr(self, renderer_name)(info)

            # 非特殊格式：使用 markdownify 将 HTML 转为 Markdown
            return self._render_html_generic(info)

        return pattern.sub(replace_match, text)

    def _render_template_table(self, info: dict) -> str:
        """渲染模板表格为Markdown"""
        table = info.get("table", [])
        if not table:
            return info.get("text", "")

        lines = []
        for row in table:
            lines.append("| " + " | ".join(str(cell) for cell in row) + " |")

        # 添加表头分隔行（如果有数据）
        if len(table) > 0:
            col_count = len(table[0])
            lines.insert(1, "| " + " | ".join(["---"] * col_count) + " |")

        # 用模板标记包裹
        class_name = info.get("class")
        if not class_name:
            # 没有特殊 class 直接输出表格，不包裹标记
            return "\n".join(lines)
        return f'<template:{class_name} start>\n' + "\n".join(lines) + f'\n<template:{class_name} end>'

    def _render_html_generic(self, info: dict) -> str:
        """使用 markdownify 将 HTML 转为 Markdown"""
        html = info.get("html", "")
        text = info.get("text", "")
        if not html and not text:
            return ""
        if not html:
            return text

        rendered = md(html, heading_style="atx", bullet_char="-")
        class_name = info.get("class")
        if not class_name:
            # 没有特殊 class 的模板直接输出文本，不包裹标记
            return rendered
        return f'<template:{class_name} start>\n{rendered}\n<template:{class_name} end>'


def convert(page: WikiPage) -> str:
    """
    便捷函数：转换WikiPage为Markdown

    Args:
        page: WikiPage对象

    Returns:
        Markdown格式字符串
    """
    converter = MarkdownConverter()
    return converter.convert_wiki(page)
