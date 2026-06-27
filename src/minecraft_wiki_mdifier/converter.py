"""
Markdown转换器

将解析后的AST转换为Markdown格式
"""

import base64
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from markdownify import markdownify as md

from minecraft_wiki_mdifier.parser import (
    Node,
    NodeType,
    TemplateInfo,
    WikiParser,
    _split_template_params,
)
from minecraft_wiki_mdifier.template_expander import TemplateExpander
from minecraft_wiki_mdifier.wiki import LANG_CONFIG, WikiPage

_logger = logging.getLogger(__name__)

# 匹配 <span class="sprite-file">...</span>，其中包含 EnvSprite img
# alt 格式："EnvSprite xxx.png：Minecraft中xxx的精灵图"，对 AI 无意义
_SPRITE_FILE_PATTERN = re.compile(
    r'<span class="sprite-file"[^>]*>.*?</span>',
    re.DOTALL,
)


def _encode_cache_value(v: str) -> str:
    """URL-safe base64 编码，避免分隔符冲突（"|" 和 "=" 不会出现在编码结果中）。"""
    return base64.urlsafe_b64encode(v.encode("utf-8")).decode("ascii")


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
NODE_RENDERERS_NEED_TEMPLATES = {
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

    # 模板名 → 专用渲染器方法名（优先级高于 FORMAT_RENDERERS）
    TEMPLATE_RENDERERS: dict[str, str] = {
        "historyline": "_render_history_line",
        "historytable": "_render_history_table",
        "only": "_render_only",
        "id": "_render_id_table",
        "id table": "_render_id_table",
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
        "infobox item": "Infobox item",
        "load achievements": "Load achievements",
        "load advancements": "Load advancements",
        "id table": "ID table",
        "crafting usage": "Crafting usage",
        "trade uses": "Trade uses",
        "drop sources": "Drop sources",
        "navbox items": "Navbox items",
        "video note": "Video note",
        "sound table/block/stone": "Sound table/block/stone",
    }

    # 模板标记格式（可被 CLI 覆盖）
    template_marker_open: str = ":::{name}"
    template_marker_close: str = ":::"

    def __init__(
        self,
        lang: str = "zh",
        max_workers: int = 10,
        template_cache: dict | None = None,
        use_persistent_cache: bool = True,
    ):
        self.parser = WikiParser()
        self.expander = TemplateExpander(lang=lang)
        self.lang = lang
        self.max_workers = max_workers
        self._use_persistent_cache = use_persistent_cache
        # 跨页共享的模板缓存（外部注入实现多批次共享）
        if template_cache is not None:
            self._template_cache = template_cache
        elif use_persistent_cache:
            from minecraft_wiki_mdifier.cache import load_cache

            self._template_cache = load_cache()
        else:
            self._template_cache = {}
        self._cache_lock = threading.Lock()
        # 未展开的模板名（驼峰映射缺失或模板不存在）
        self._unresolved: set[str] = set()
        self._unresolved_lock = threading.Lock()
        # 取消标志（convert_many 检查）
        self._cancelled = False
        self._cancel_lock = threading.Lock()

    def cancel(self) -> None:
        """请求取消批量转换（仅 convert_many 有效，单页 convert_wiki 不响应）"""
        with self._cancel_lock:
            self._cancelled = True

    @property
    def unresolved_templates(self) -> frozenset[str]:
        """返回本次转换中未展开的模板名集合（只读视图）"""
        with self._unresolved_lock:
            return frozenset(self._unresolved)

    def is_cancelled(self) -> bool:
        """返回取消标志当前状态"""
        with self._cancel_lock:
            return self._cancelled

    def flush_cache(self) -> None:
        """将当前模板缓存保存到磁盘（供后续运行复用）"""
        if not self._use_persistent_cache:
            return
        from minecraft_wiki_mdifier.cache import save_cache

        with self._cache_lock:
            save_cache(self._template_cache)

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
        expanded_templates = self._expand_all_templates(templates, title)

        # 阶段4: 生成Markdown
        return self._generate_markdown(nodes, expanded_templates, title)

    def _expand_all_templates(
        self, templates: dict[str, TemplateInfo], page_title: str | None = None
    ) -> dict[str, dict]:
        """
        并发展开所有模板（10x 加速）

        Args:
            templates: 模板字典
            page_title: 页面标题（用于 bucket 查询默认值）

        Returns:
            展开后的模板字典
        """
        expanded = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_name = {
                executor.submit(self._expand_template, key, info.params, page_title): key
                for key, info in templates.items()
            }

            # 收集结果
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    expanded[name] = future.result()
                except Exception as e:
                    # 单个模板失败不应中断整体
                    _logger.debug("Template %s expand failed: %s, using fallback", name, e)
                    expanded[name] = self._fallback_template(name, templates[name].params)

        return expanded

    def _expand_template(
        self, name: str, params: dict[str, str], page_title: str | None = None
    ) -> dict:
        """
        展开单个模板（带跨页缓存）

        Args:
            name: 模板名称
            params: 模板参数
            page_title: 页面标题（用于 bucket 查询默认值）

        Returns:
            展开结果 dict
        """
        # 提取模板名（可能带序号 ItemLink:0 -> ItemLink）
        template_name = name.split(":")[0] if ":" in name else name
        api_name = self._resolve_template_name(template_name)
        parts = [api_name]
        for key, value in params.items():
            if key.isdigit():
                parts.append(_encode_cache_value(value))
            else:
                parts.append(f"{_encode_cache_value(key)}={_encode_cache_value(value)}")
        cache_key = "|".join(parts)
        cache_key = f"{self.lang}:{cache_key}"

        # 缓存命中
        with self._cache_lock:
            if cache_key in self._template_cache:
                return self._template_cache[cache_key]

        # 缓存未命中 → 实际调用
        template_call = "{{" + cache_key + "}}"
        try:
            expanded = self.expander.expand(template_call, page_title)
            result = {
                "name": name,
                "class": expanded["class"],
                "text": expanded["text"],
                "html": expanded["html"],
                "format": expanded.get("format", "text"),
                "table": expanded.get("table"),
                "template_name": expanded.get("template_name"),
                "params": params,  # 原始参数，渲染器需要用来做语义化渲染
            }
        except Exception as e:
            _logger.debug("Template %s expand failed: %s, using fallback", name, e)
            result = self._fallback_template(name, params)

        # 记录未展开的模板（API 返回 class="new" 或展开失败 class="error"）
        if result.get("class") in ("new", "error"):
            with self._unresolved_lock:
                self._unresolved.add(name)

        with self._cache_lock:
            self._template_cache[cache_key] = result
        return result

    def _resolve_template_name(self, name: str) -> str:
        """解析模板 API 名称：手工映射 → 自动 PascalCase"""
        # 1. 手工映射优先
        if name.lower() in self.CAMEL_CASE_TEMPLATES:
            return self.CAMEL_CASE_TEMPLATES[name.lower()]

        # 2. 自动尝试 PascalCase（仅对全小写、无空格的简单名称）
        cleaned = name.replace(" ", "").replace("-", "")
        if cleaned.isalpha() and cleaned.islower():
            pascal = cleaned.capitalize()
            if pascal != name:
                return pascal
        return name

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
            "class": "error",
            "text": f"[{name}: {params_str}]",
            "html": None,
            "format": "text",
            "table": None,
            "params": params,
        }

    def _generate_markdown(
        self, nodes: list[Node], expanded_templates: dict[str, dict], title: str
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
        lines = [f"# {title}", ""]

        for node in nodes:
            lines.append(self._render_node(node, expanded_templates))

        return "\n".join(lines)

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
            return ""
        renderer = getattr(self, renderer_name)
        # 根据渲染器签名决定是否传 expanded_templates
        if renderer_name in NODE_RENDERERS_NEED_TEMPLATES:
            return renderer(node, expanded_templates)
        return renderer(node)

    def _render_horizontal_rule(self, node: Node) -> str:
        """水平线"""
        return "---\n"

    def _render_heading(self, node: Node) -> str:
        """渲染标题节点"""
        level = min(node.attrs.get("level", 2), 6)
        return f"{'#' * level} {node.content}\n"

    def _render_paragraph(self, node: Node, expanded_templates: dict[str, dict]) -> str:
        """渲染段落节点"""
        content = self._replace_template_placeholders(node.content, expanded_templates)
        return f"{content}\n"

    def _render_list(self, node: Node, expanded_templates: dict[str, dict]) -> str:
        """渲染列表节点"""
        lines = []
        list_type = node.attrs.get("list_type", "ul")
        marker = "- " if list_type == "ul" else "1. "
        for item in node.children:
            if item.type == NodeType.LIST_ITEM:
                content = self._replace_template_placeholders(item.content, expanded_templates)
                lines.append(f"{marker}{content}")
        lines.append("")
        return "\n".join(lines)

    def _render_table(self, node: Node) -> str:
        """渲染表格节点"""
        if not node.children:
            return ""
        lines = ["| " + " | ".join(c.content for c in node.children) + " |"]
        lines.append("| " + " | ".join(["---"] * len(node.children)) + " |")
        lines.append("")
        return "\n".join(lines)

    def _render_text(self, node: Node, expanded_templates: dict[str, dict]) -> str:
        """渲染文本节点"""
        return self._replace_template_placeholders(node.content, expanded_templates)

    def _replace_template_placeholders(self, text: str, expanded_templates: dict[str, dict]) -> str:
        """
        替换文本中的模板占位符

        Args:
            text: 文本内容
            expanded_templates: 展开后的模板字典

        Returns:
            替换后的文本
        """
        pattern = re.compile(r"\{TEMPLATE:([^{}]+?)\}")

        def replace_match(match):
            template_name = match.group(1).lower()
            info = expanded_templates.get(template_name)
            if not info:
                return match.group(0)

            # 优先通过模板名专用渲染器查找
            # info["name"] 可能是 "historytable:0"，需要去掉 :N 后缀
            raw_key = info.get("name", "").lower()
            template_key = raw_key.split(":")[0] if ":" in raw_key else raw_key
            renderer_name = self.TEMPLATE_RENDERERS.get(template_key)
            if not renderer_name:
                # 降级：通过 format 查找渲染方法
                fmt = info.get("format", "text")
                renderer_name = self.FORMAT_RENDERERS.get(fmt)
            if renderer_name:
                return getattr(self, renderer_name)(info)

            # 非特殊格式：使用 markdownify 将 HTML 转为 Markdown
            return self._render_html_generic(info)

        return pattern.sub(replace_match, text)

    def _wrap_template(self, class_name: str | None, body: str) -> str:
        """用模板标记包裹内容（class_name 为 None 时直接返回）"""
        if not class_name:
            return body
        return (
            self.template_marker_open.format(name=class_name)
            + "\n"
            + body
            + "\n"
            + self.template_marker_close.format(name=class_name)
            + "\n"
        )

    def _render_template_table(self, template_data: dict) -> str:
        """渲染模板表格为Markdown"""
        table = template_data.get("table", [])
        if not table:
            return template_data.get("text", "")

        lines = []
        for row in table:
            lines.append("| " + " | ".join(str(cell) for cell in row) + " |")

        # 添加表头分隔行（如果有数据）
        if len(table) > 0:
            col_count = len(table[0])
            lines.insert(1, "| " + " | ".join(["---"] * col_count) + " |")

        # 优先用语义模板名，回退到 HTML class
        name = template_data.get("template_name") or template_data.get("class")
        if not name:
            return "\n".join(lines)
        return self._wrap_template(name, "\n".join(lines))

    def _render_html_generic(self, template_data: dict) -> str:
        """使用 markdownify 将 HTML 转为 Markdown"""
        html = template_data.get("html", "")
        text = template_data.get("text", "")
        if not html and not text:
            return ""
        if not html:
            return text

        # 移除 EnvSprite 的 sprite-file span（alt 文本 "EnvSprite xxx.png：Minecraft中xxx的精灵图" 对 AI 无意义）
        html = _SPRITE_FILE_PATTERN.sub("", html)

        rendered = md(html, heading_style="atx", bullet_char="-")

        # 替换相对路径为完整 URL
        static_base = LANG_CONFIG[self.lang]["static_base"]
        rendered = rendered.replace("/images/", f"{static_base}/images/")
        rendered = rendered.replace("/w/", f"{static_base}/w/")

        name = template_data.get("template_name") or template_data.get("class")
        if not name:
            return rendered
        return self._wrap_template(name, rendered)

    def _render_history_line(self, info: dict) -> str:
        """
        渲染 HistoryLine 模板为时间线格式

        参数格式（混合位置+命名）：
        {{HistoryLine|[版本标志]|[版本号]|[日期]|[描述...]}}
        {{HistoryLine|||dev=日期|text}}
        {{HistoryLine|版本标志|版本号|dev=日期|link=URL|text}}

        输出：- **版本号** — 描述
        """
        params = info.get("params", info.get("text", ""))
        if isinstance(params, str):
            # fallback: text 模式时 params 是字符串
            return self._wrap_template("HistoryLine", params)

        # 取位置参数作为版本和描述
        version_label = params.get("1", "").strip()
        version_num = params.get("2", "").strip()
        description = params.get("3", "").strip()

        # 找最后一个非键名的值（描述文本）
        # 位置参数之后的参数可能是描述
        for key in sorted(params.keys(), key=lambda k: (not k.isdigit(), k)):
            if key.isdigit():
                v = params[key].strip()
                if v and v not in (version_label, version_num) and not v.startswith("http"):
                    description = v

        # 组合版本标识
        if version_num:
            version_str = version_num
        elif version_label:
            version_str = version_label
        else:
            version_str = ""

        # 收集额外元信息（dev=, exp=, link=, xbox= 等）
        meta_parts = []
        for key, value in sorted(params.items()):
            if not key.isdigit() and value.strip():
                meta_parts.append(value.strip())

        if description:
            line = f"- **{version_str}**"
            if meta_parts:
                line += f" — {description} ({', '.join(meta_parts)})"
            else:
                line += f" — {description}"
        elif version_str:
            line = f"- **{version_str}**"
            if meta_parts:
                line += f" ({', '.join(meta_parts)})"
        else:
            return ""

        return self._wrap_template("HistoryLine", line)

    def _render_history_table(self, info: dict) -> str:
        """
        渲染 HistoryTable 模板为时间线格式

        HistoryTable 的每个 param value 都是一个 {{HistoryLine|...}} wikitext 字符串。
        我们直接解析这些 wikitext 字符串，生成结构化时间线输出。

        输出：
        ## 历史

        - **1.20** — 发生了变化
        - **1.19** — 增加了新特性
        """
        params = info.get("params", {})
        if not params:
            return self._wrap_template("HistoryTable", "")

        lines = []
        for key in sorted(params.keys(), key=lambda k: (not k.isdigit(), k)):
            value = params[key].strip()
            if not value:
                continue

            # 如果 value 包含 {{HistoryLine，说明是嵌套的 wikitext
            if "{{HistoryLine" in value:
                # 解析 {{HistoryLine|...}} wikitext
                # _split_template_params 可以正确处理嵌套模板
                inner = value.lstrip("{").rstrip("}").rstrip("{").rstrip("}")
                parts = _split_template_params(inner)
                if not parts:
                    continue

                # 解析参数（第一个部分是模板名本身）
                inner_params: dict[str, str] = {}
                for i, part in enumerate(parts[1:], start=1):
                    part = part.strip()
                    if not part:
                        continue
                    if "=" in part:
                        k, v = part.split("=", 1)
                        inner_params[k.strip()] = v.strip()
                    else:
                        inner_params[str(i)] = part

                # 提取版本和描述
                version_label = inner_params.get("1", "").strip()
                version_num = inner_params.get("2", "").strip()
                description = inner_params.get("3", "").strip()

                # 找描述（可能在后续数字参数中）
                if not description:
                    for k in sorted(inner_params.keys(), key=lambda x: (not x.isdigit(), x)):
                        if k.isdigit() and inner_params[k].strip():
                            v = inner_params[k].strip()
                            if v not in (version_label, version_num) and not v.startswith("http"):
                                description = v
                                break

                # 找元信息
                meta_parts = []
                for k, v in sorted(inner_params.items()):
                    if not k.isdigit() and v.strip():
                        meta_parts.append(v.strip())

                if version_num:
                    version_str = version_num
                elif version_label:
                    version_str = version_label
                else:
                    version_str = ""

                if description:
                    line = f"- **{version_str}**"
                    if meta_parts:
                        line += f" — {description} ({', '.join(meta_parts)})"
                    else:
                        line += f" — {description}"
                elif version_str:
                    line = f"- **{version_str}**"
                    if meta_parts:
                        line += f" ({', '.join(meta_parts)})"
                else:
                    continue

                lines.append(line)

        if not lines:
            return self._wrap_template("HistoryTable", "")

        return self._wrap_template("HistoryTable", "\n".join(lines))

    def _render_only(self, info: dict) -> str:
        """
        渲染 Only 模板为版本提示格式

        格式：{{Only|条件|内容}}
        输出：> 仅 条件：内容
        """
        params = info.get("params", info.get("text", ""))
        if isinstance(params, str):
            return self._wrap_template("Only", params)

        # Only 通常是位置参数
        condition = params.get("1", "").strip()
        content = params.get("2", "").strip()
        if not content:
            # 内容可能在后续位置参数中
            for key in sorted(params.keys(), key=lambda k: (not k.isdigit(), k)):
                if key.isdigit() and params[key].strip() and params[key].strip() != condition:
                    content = params[key].strip()
                    break

        if condition and content:
            return self._wrap_template("Only", f"> 仅 {condition}：{content}")
        elif content:
            return self._wrap_template("Only", content)
        return ""

    def _render_id_table(self, info: dict) -> str:
        """
        渲染 ID / ID table 模板为结构化表格

        格式：{{ID table|数字ID=256|字符串ID=minecraft:iron_ingot}}
        输出：| 类型 | 值 |
              |------|-----|
              | 数字 | 256 |
              | 字符串 | iron_ingot |
        """
        params = info.get("params", info.get("text", ""))
        if isinstance(params, str):
            return self._wrap_template("ID table", params)

        # 收集所有键值对
        rows = []
        for key, value in sorted(params.items()):
            if key.isdigit():
                continue
            key_str = key.strip()
            value_str = value.strip()
            if not value_str:
                continue
            # 翻译常见键名
            label = key_str
            if key_str.lower() in ("数字id", "数字", "numeric id", "数字 ID"):
                label = "数字"
            elif key_str.lower() in ("字符串id", "字符串", "string id", "字符串 ID"):
                label = "字符串"
            elif key_str.lower() in ("物品id", "物品", "item id", "物品 ID"):
                label = "物品"
            elif key_str.lower() in ("方块id", "方块", "block id", "方块 ID"):
                label = "方块"
            rows.append([label, value_str])

        if not rows:
            return self._wrap_template("ID table", "")

        lines = ["| 类型 | 值 |", "|------|-----|"]
        for label, value in rows:
            lines.append(f"| {label} | {value} |")

        return self._wrap_template("ID table", "\n".join(lines))
