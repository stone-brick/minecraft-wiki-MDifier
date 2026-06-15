"""
MediaWiki语法解析器

解析WikiText，提取结构化信息
"""

import re
from dataclasses import dataclass, field
from enum import Enum, auto


def _parse_template_name(template_str: str) -> str:
    """
    从模板字符串提取模板名，移除命名空间前缀

    Args:
        template_str: 模板内容（如 "Hatnote|text" 或 "ItemLink:0"）

    Returns:
        纯模板名（如 "Hatnote" 或 "ItemLink"）
    """
    name = template_str.split("|")[0].strip()
    if ":" in name:
        name = name.split(":", 1)[1]
    return name


class NodeType(Enum):
    """AST节点类型"""

    TEXT = auto()
    HEADING = auto()
    PARAGRAPH = auto()
    LIST = auto()
    LIST_ITEM = auto()
    LINK = auto()
    IMAGE = auto()
    TABLE = auto()
    TEMPLATE = auto()
    CODE = auto()
    HORIZONTAL_RULE = auto()


@dataclass
class Node:
    """AST节点"""

    type: NodeType
    content: str = ""
    children: list["Node"] = field(default_factory=list)
    attrs: dict = field(default_factory=dict)  # 模板参数等

    def __repr__(self):
        return f"Node({self.type.name}, content={self.content[:30]!r})"


@dataclass
class TemplateInfo:
    """模板信息"""

    name: str  # 模板名称（不含命名空间）
    params: dict[str, str]  # 参数名: 值


class WikiParser:
    """
    MediaWiki语法解析器

    将WikiText解析为AST
    """

    # 链接匹配：[[链接|显示文本]]
    LINK_PATTERN = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]")

    # 图片匹配：[[文件:xxx|参数]]
    IMAGE_PATTERN = re.compile(r"\[\[文件:([^\]|]+?)(?:\|([^\]]+?))?\]\]", re.IGNORECASE)

    # 标题匹配：== 标题 ==
    HEADING_PATTERN = re.compile(r"^(=+)\s*(.+?)\s*(=+)$", re.MULTILINE)

    def __init__(self):
        self.templates: dict[str, TemplateInfo] = {}
        self._template_counter: dict[str, int] = {}

    def parse(self, wikitext: str) -> list[Node]:
        """
        解析WikiText为AST

        Args:
            wikitext: WikiText内容

        Returns:
            AST节点列表
        """
        self.templates.clear()

        # 预处理：移除注释 <!-- -->
        wikitext = re.sub(r"<!--.*?-->", "", wikitext, flags=re.DOTALL)

        lines = wikitext.split("\n")
        nodes = []
        current_paragraph: list[str] = []
        in_table = False
        table_nodes: list[Node] = []

        def flush_paragraph():
            nonlocal current_paragraph
            if current_paragraph:
                text = " ".join(current_paragraph)
                if text.strip():
                    nodes.append(Node(type=NodeType.PARAGRAPH, content=self._process_inline(text)))
                current_paragraph = []

        for line in lines:
            stripped = line.strip()

            # 跳过空行
            if not stripped:
                flush_paragraph()
                if in_table:
                    in_table = False
                    nodes.extend(table_nodes)
                    table_nodes = []
                continue

            # 标题
            heading_match = self.HEADING_PATTERN.match(stripped)
            if heading_match:
                flush_paragraph()
                level = len(heading_match.group(1))
                text = heading_match.group(2)
                nodes.append(
                    Node(
                        type=NodeType.HEADING,
                        content=self._process_inline(text),
                        attrs={"level": level},
                    )
                )
                continue

            # 表格
            if stripped.startswith("{|") or stripped.startswith("!!"):
                flush_paragraph()
                in_table = True
                table_nodes.append(self._parse_table_row(stripped))
                continue

            if in_table and stripped.startswith("|}"):
                in_table = False
                nodes.extend(table_nodes)
                table_nodes = []
                continue

            if in_table and stripped.startswith("|-"):
                # 行分隔符，跳过
                continue

            if in_table:
                table_nodes.append(self._parse_table_row(stripped))
                continue

            # 列表
            if stripped.startswith("*") or stripped.startswith("#"):
                flush_paragraph()
                nodes.append(self._parse_list(stripped))
                continue

            # 分隔线
            if stripped.startswith("----"):
                flush_paragraph()
                nodes.append(Node(type=NodeType.HORIZONTAL_RULE))
                continue

            # 普通段落
            current_paragraph.append(stripped)

        flush_paragraph()
        if in_table:
            nodes.extend(table_nodes)

        return nodes

    def _process_inline(self, text: str) -> str:
        """
        处理行内元素（链接、图片、模板引用）

        Args:
            text: 文本内容

        Returns:
            处理后的文本
        """
        # 先提取模板
        text = self._extract_templates(text)

        # 处理图片
        text = self.IMAGE_PATTERN.sub(lambda m: self._format_image(m), text)

        # 处理链接
        text = self.LINK_PATTERN.sub(lambda m: self._format_link(m), text)

        return text

    def _extract_templates(self, text: str) -> str:
        """
        提取模板并存储，支持跨行模板

        Args:
            text: 包含模板的文本

        Returns:
            替换后的文本
        """
        result = []
        i = 0
        stack: list[int] = []  # 栈：记录每次 {{ 出现时的位置
        template_start = -1

        while i < len(text):
            if i + 1 < len(text) and text[i : i + 2] == "{{":
                if not stack:
                    template_start = i
                stack.append(i)
                i += 2
            elif i + 1 < len(text) and text[i : i + 2] == "}}":
                if stack:
                    stack.pop()
                    if not stack and template_start >= 0:
                        template_str = text[template_start + 2 : i]
                        key = self._parse_template(template_str)
                        result.append(f"{{TEMPLATE:{key}}}")
                        template_start = -1
                i += 2
            else:
                if not stack:
                    result.append(text[i])
                i += 1

        return "".join(result)

    def _parse_template(self, template_str: str) -> str:
        """
        解析模板字符串并存储，支持同名多次出现

        Args:
            template_str: 模板内容（不含{{}}）

        Returns:
            唯一标识键（如 "ItemLink:0", "ItemLink:1"）
        """
        name = _parse_template_name(template_str)
        parts = template_str.split("|")

        params = {}
        for i, part in enumerate(parts[1:], start=1):
            part = part.strip()
            if "=" in part:
                key, value = part.split("=", 1)
                params[key.strip()] = value.strip()
            else:
                params[str(i)] = part

        # 生成唯一键：name:序号（同名模板多次出现时序号递增）
        key = f"{name.lower()}:{self._template_counter.get(name.lower(), 0)}"
        self._template_counter[name.lower()] = self._template_counter.get(name.lower(), 0) + 1

        info = TemplateInfo(name=name, params=params)
        self.templates[key] = info
        return key

    def _format_link(self, match: re.Match) -> str:
        """
        格式化链接

        Args:
            match: 正则匹配对象

        Returns:
            Markdown格式链接
        """
        target = match.group(1)
        display = match.group(2) or target
        return f"[{display}]({target})"

    def _format_image(self, match: re.Match) -> str:
        """
        格式化图片

        Args:
            match: 正则匹配对象

        Returns:
            Markdown格式图片
        """
        filename = match.group(1)
        caption = match.group(2) or ""

        # 从文件名提取描述
        desc = caption.split("|")[-1].strip() if caption else filename
        return f"![{desc}]({filename})"

    def _parse_table_row(self, row: str) -> Node:
        """
        解析表格行

        Args:
            row: 表格行文本

        Returns:
            表格节点
        """
        cells = []
        # 分割单元格
        parts = re.split(r"\|\|", row)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # 移除单元格标记
            part = re.sub(r"^\|", "", part)
            cells.append(Node(type=NodeType.TEXT, content=self._process_inline(part)))

        return Node(type=NodeType.TABLE, content="", children=cells, attrs={"headers": False})

    def _parse_list(self, line: str) -> Node:
        """
        解析列表

        Args:
            line: 列表行文本

        Returns:
            列表节点
        """
        items = []
        marker = "*" if line.lstrip().startswith("*") else "#"
        parts = line.split(marker)
        parts = [p.strip() for p in parts if p.strip()]

        list_type = "ul" if marker == "*" else "ol"

        for item in parts:
            items.append(Node(type=NodeType.LIST_ITEM, content=self._process_inline(item)))

        return Node(type=NodeType.LIST, content="", children=items, attrs={"list_type": list_type})

    def get_templates(self) -> dict[str, TemplateInfo]:
        """
        获取解析过程中发现的模板

        Returns:
            模板字典
        """
        return self.templates.copy()
