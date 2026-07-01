"""
Pandoc 预处理 + 模板渲染模块

用 pypandoc 替代 WikiParser 做预处理，无法处理的模板保留为 ```{=mediawiki}``` 块，
通过 TemplateExpander 展开后再用 v0.1.3 渲染逻辑输出 Markdown。

流程：
WikiText → pypandoc(commonmark_x+raw_attribute)
         → 正则匹配 .{=mediawiki} 块 → expander.expand() → v0.1.3 渲染器
         → 清理残留语法
"""

import re

import pypandoc
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from minecraft_wiki_mdifier.template_expander import TemplateExpander
from minecraft_wiki_mdifier.wiki import LANG_CONFIG

# =============================================================================
# 正则
# =============================================================================

# 匹配 ```{=mediawiki} 块（模板残留）
_MEDIAWIKI_BLOCK_PATTERN = re.compile(
    r"```\{=mediawiki\}\s*(.*?)\s*```",
    re.DOTALL,
)

# 匹配内联模板 `{{...}}`{=mediawiki}
_MEDIAWIKI_INLINE_PATTERN = re.compile(
    r"`(\{\{.*?\}\})`\{=mediawiki\}",
    re.DOTALL,
)

# 匹配 <span class="sprite-file">...</span>，alt 文本对 AI 无意义
_SPRITE_FILE_PATTERN = re.compile(
    r'<span class="sprite-file"[^>]*>.*?</span>',
    re.DOTALL,
)

# =============================================================================
# 注册表（来自 v0.1.3 converter.py）
# =============================================================================

# format → 渲染方法名
FORMAT_RENDERERS: dict[str, str] = {
    "infobox_table": "_render_template_table",
    "table": "_render_template_table",
    "mcui": "_render_template_table",
}

# 模板名（小写）→ 专用渲染方法名（优先级高于 FORMAT_RENDERERS）
TEMPLATE_RENDERERS: dict[str, str] = {
    "historyline": "_render_history_line",
    "historytable": "_render_history_table",
    "only": "_render_only",
    "id": "_render_id_table",
    "id table": "_render_id_table",
    "navbox items": "_render_navbox_items",
    "bv": "_render_bv",
}

# 已知需要驼峰转写的模板名（小写 → 正确名）
# parser 提取时统一小写，但 MediaWiki 区分大小写
CAMEL_CASE_TEMPLATES: dict[str, str] = {
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

# =============================================================================
# 入口
# =============================================================================


def wikitext_to_format(
    wikitext: str,
    expander: TemplateExpander,
    page_title: str,
    output_format: str,
    lang: str = "zh",
) -> str:
    """
    将 WikiText 转换为指定格式

    Args:
        wikitext: Wiki 文本
        expander: TemplateExpander 实例
        page_title: 页面标题（用于模板展开）
        output_format: 输出格式 (markdown, html, docx, pdf)
        lang: 语言代码

    Returns:
        转换后的字符串
    """
    # pypandoc 预处理：commonmark_x + raw_attribute 保留无法处理的模板为 {=mediawiki} 块
    result = pypandoc.convert_text(
        wikitext,
        f"{output_format}+raw_attribute",
        format="mediawiki",
        extra_args=["--from", "mediawiki"],
    )
    # 替换 {=mediawiki} 块为渲染后的 Markdown
    return _replace_mediawiki_blocks(result, expander, page_title, lang)


# =============================================================================
# 模板块替换
# =============================================================================


def _replace_mediawiki_blocks(
    text: str,
    expander: TemplateExpander,
    page_title: str,
    lang: str,
) -> str:
    """替换文本中的 {=mediawiki} 块（块级和内联）为展开后的模板内容"""

    def block_replacer(match: re.Match) -> str:
        template_content = match.group(1).strip()
        if not template_content:
            return ""
        try:
            expanded = expander.expand(template_content, page_title)
            expanded_text = expanded.get("text", "")
            if expanded_text.startswith("[[:Template:") and expanded_text.endswith("]]"):
                return match.group(0)
            return _render_template_to_markdown(expanded, lang)
        except Exception:
            return match.group(0)

    def inline_replacer(match: re.Match) -> str:
        template_content = match.group(1).strip()
        if not template_content:
            return match.group(0)
        try:
            expanded = expander.expand(template_content, page_title)
            expanded_text = expanded.get("text", "")
            if expanded_text.startswith("[[:Template:") and expanded_text.endswith("]]"):
                return match.group(0)
            return _render_template_to_markdown(expanded, lang)
        except Exception:
            return match.group(0)

    # 先替换块级模板
    text = _MEDIAWIKI_BLOCK_PATTERN.sub(block_replacer, text)
    # 再替换内联模板
    text = _MEDIAWIKI_INLINE_PATTERN.sub(inline_replacer, text)
    # 清理 Pandoc 直接输出的 MediaWiki 残留语法
    text = _strip_mediawiki_syntax(text)
    return text


# =============================================================================
# 渲染分发（来自 v0.1.3 converter.py）
# =============================================================================


def _render_template_to_markdown(expanded: dict, lang: str) -> str:
    """
    将展开的模板渲染为 Markdown。
    优先 TEMPLATE_RENDERERS（专用渲染器），次优 FORMAT_RENDERERS，
    兜底 markdownify 或 wikitext 表格处理。
    """
    # 优先通过模板名专用渲染器查找
    template_name = expanded.get("template_name", "") or expanded.get("name", "") or ""
    key = template_name.lower()
    renderer_name = TEMPLATE_RENDERERS.get(key)
    if not renderer_name:
        fmt = expanded.get("format", "text")
        renderer_name = FORMAT_RENDERERS.get(fmt)
    if renderer_name:
        return globals()[renderer_name](expanded, lang)

    # 文本格式：检查是否是 WikiTable 格式（text 以 {| 开头）
    text = expanded.get("text", "")
    if text.strip().startswith("{|"):
        cleaned = _clean_loot_wikitext(text)
        try:
            raw = pypandoc.convert_text(
                cleaned, "gfm", format="mediawiki", extra_args=["--from", "mediawiki"]
            )
            return _clean_pandoc_output(raw)
        except Exception:
            return _wikitable_to_markdown(cleaned)

    return _render_html_generic(expanded, lang)


def _wrap_template(class_name: str | None, body: str) -> str:
    """用模板标记包裹内容（class_name 为 None 时直接返回）"""
    if not class_name:
        return body
    return f":::{class_name}\n{body}\n:::\n"


def _render_template_table(expanded: dict, lang: str) -> str:
    """渲染模板表格为 Markdown（v0.1.3 逻辑）"""

    def format_cell(cell: str) -> str:
        """格式化单元格：换行转为 <br/>"""
        return str(cell).replace("\n", "<br/>")

    table = expanded.get("table", [])
    if not table:
        return expanded.get("text", "")

    lines = []
    for row in table:
        lines.append("| " + " | ".join(format_cell(cell) for cell in row) + " |")

    if len(table) > 0:
        col_count = len(table[0])
        lines.insert(1, "| " + " | ".join(["---"] * col_count) + " |")

    name = expanded.get("template_name") or expanded.get("class")
    if not name:
        return "\n".join(lines)
    return _wrap_template(name, "\n".join(lines))


def _render_html_generic(expanded: dict, lang: str) -> str:
    """使用 markdownify 将 HTML 转为 Markdown（v0.1.3 逻辑）"""
    html = expanded.get("html", "")
    text = expanded.get("text", "")
    if not html and not text:
        return ""
    if not html:
        return text

    # 移除 EnvSprite 的 sprite-file span
    html = _SPRITE_FILE_PATTERN.sub("", html)

    rendered = md(html, heading_style="atx", bullet_char="-")

    # 替换相对路径为完整 URL
    static_base = LANG_CONFIG[lang]["static_base"]
    rendered = rendered.replace("/images/", f"{static_base}/images/")
    rendered = rendered.replace("/w/", f"{static_base}/w/")

    name = expanded.get("template_name") or expanded.get("class")
    if not name:
        return rendered
    return _wrap_template(name, rendered)


def _render_history_line(info: dict, lang: str) -> str:
    """
    渲染 HistoryLine 模板为时间线格式
    解析 action=parse 返回的 HTML 表格行
    输出：- **版本号** — 描述
    """
    html = info.get("html", "")
    text = info.get("text", "")

    # 如果有 HTML，解析它
    if html:
        soup = BeautifulSoup(html, "html.parser")
        tr = soup.find("tr")
        if tr:
            ths = tr.find_all("th")
            tds = tr.find_all("td")

            version_str = ths[0].get_text(strip=True) if ths else ""
            description = tds[-1].get_text(strip=True) if tds else ""

            if description:
                line = f"- **{version_str}** — {description}" if version_str else f"- {description}"
            elif version_str:
                line = f"- **{version_str}**"
            else:
                return ""

            return _wrap_template("HistoryLine", line)

    # Fallback 到纯文本
    if text:
        return _wrap_template("HistoryLine", text)

    return ""


def _render_history_table(info: dict, lang: str) -> str:
    """
    渲染 HistoryTable 模板为时间线格式
    解析 action=parse 返回的 HTML 表格结构
    """
    html = info.get("html", "")
    if not html:
        return _wrap_template("HistoryTable", "")

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return _wrap_template("HistoryTable", "")

    lines = []
    current_section = ""

    for tr in table.find_all("tr"):
        ths = tr.find_all("th")
        tds = tr.find_all("td")

        # Section header row: 只有 th 且 colspan >= 6
        if ths and not tds:
            first_th = ths[0]
            if first_th.get("colspan") and int(first_th.get("colspan", 0)) >= 6:
                current_section = first_th.get_text(strip=True)
                continue

        # Data row: 有 td 的行
        if tds:
            # 版本号在第一个 th 中（如果有）
            version_str = ths[0].get_text(strip=True) if ths else ""

            # 描述在最后一个 td 中
            description = tds[-1].get_text(strip=True) if tds else ""

            if description:
                line = f"- **{version_str}** — {description}" if version_str else f"- {description}"
                if current_section:
                    line = f"[{current_section}] {line}"
                lines.append(line)

    if not lines:
        return _wrap_template("HistoryTable", "")

    return _wrap_template("HistoryTable", "\n".join(lines))


def _render_only(info: dict, lang: str) -> str:
    """
    渲染 Only 模板为版本提示格式
    {{Only|条件|内容}}
    输出：> 仅 条件：内容
    """
    params = info.get("params", info.get("text", ""))
    if isinstance(params, str):
        return _wrap_template("Only", params)

    condition = str(params.get("1", "")).strip()
    content = str(params.get("2", "")).strip()
    if not content:
        for key in sorted(params.keys(), key=lambda k: (not str(k).isdigit(), k)):
            v = str(params[key]).strip()
            if v and v != condition:
                content = v
                break

    if condition and content:
        return _wrap_template("Only", f"> 仅 {condition}：{content}")
    elif content:
        return _wrap_template("Only", content)
    return ""


def _render_id_table(info: dict, lang: str) -> str:
    """
    渲染 ID / ID table 模板为结构化表格
    使用 action=parse 返回的 table 数据
    """
    table = info.get("table", [])
    if not table:
        # Fallback 到纯文本
        text = info.get("text", "")
        return _wrap_template("ID table", text) if text else ""

    def format_cell(cell: str) -> str:
        """格式化单元格：换行转为 <br/>"""
        return str(cell).replace("\n", "<br/>")

    lines = []
    for row in table:
        lines.append("| " + " | ".join(format_cell(cell) for cell in row) + " |")

    if len(table) > 0:
        col_count = len(table[0])
        lines.insert(1, "| " + " | ".join(["---"] * col_count) + " |")

    return _wrap_template("ID table", "\n".join(lines))


def _render_navbox_items(info: dict, lang: str) -> str:
    """
    渲染 Navbox items 模板为列表格式
    提取 HTML 中的分类列表
    """
    html = info.get("html", "")
    if not html:
        text = info.get("text", "")
        return _wrap_template("Navbox items", text) if text else ""

    soup = BeautifulSoup(html, "html.parser")

    # 提取所有列表项
    items = []
    for li in soup.find_all("li"):
        text = li.get_text(strip=True)
        if text:
            items.append(text)

    if items:
        # 用逗号连接列表项
        content = "、".join(items)
        return _wrap_template("Navbox items", content)

    # Fallback: 用 markdownify 处理
    return _render_html_generic(info, lang)


def _render_bv(info: dict, lang: str) -> str:
    """
    渲染 bv (Bilibili 视频) 模板
    提取 iframe src 为视频链接
    """
    html = info.get("html", "")
    if not html:
        text = info.get("text", "")
        return _wrap_template("bv", text) if text else ""

    soup = BeautifulSoup(html, "html.parser")
    iframe = soup.find("iframe", class_="embedvideo-player")
    if iframe:
        src = iframe.get("src", "")
        if src:
            # 转换为 Markdown 链接格式
            return _wrap_template("bv", f"[视频]({src})")

    # Fallback: 用 markdownify 处理
    return _render_html_generic(info, lang)


# =============================================================================
# 清理辅助（来自 refactor/document-blocks）
# =============================================================================


def _strip_mediawiki_syntax(text: str) -> str:
    """
    清理 Pandoc 直接输出的 MediaWiki 残留语法：
    - {.wikilink} 属性
    - [text](url "title") 中的 title 悬浮提示
    - [[File:]] [[Category:]] [[|]]
    - 剩余的 [{=mediawiki}] 标记
    """
    # 清理 {.classname} 和 {#idname} 后缀（MediaWiki 元素属性语法）
    text = re.sub(r"\{[.#][^{}]*\}", "", text)
    # 清理 title 属性：![](url "title") → ![](url)，[](url "title") → [](url)
    text = re.sub(r'(!?\[.*?\]\([^)]*)\s+"[^"]*"\)', r"\1)", text)
    # 清理 [[File:]] [[Category:]]
    text = re.sub(r"\[\[File:.*?\]\]", "", text)
    text = re.sub(r"\[\[Category:.*?\]\]", "", text)
    # 清理 [[|]] 格式的管道链接
    text = re.sub(r"\[\[([^\]|]+?)\|([^\]]*?)\]\]", r"[\2](\1)", text)
    # 清理空的 [](/)
    text = re.sub(r"!\[\]\(\)", "", text)
    # 清理 mediawiki 标记残留
    text = re.sub(r"`\{=mediawiki\}`", "", text)
    return text


def _clean_loot_wikitext(text: str) -> str:
    """清理跨行 style/rowspan 等后的 wikitext"""
    lines = text.strip().splitlines()
    result = []
    for line in lines:
        line = re.sub(r"\s*style=\"[^\"]*\"", "", line)
        line = re.sub(r"\s*class=\"[^\"]*\"", "", line)
        line = re.sub(r"\s*rowspan=\"[^\"]*\"", "", line)
        line = re.sub(r"\s*colspan=\"[^\"]*\"", "", line)
        line = re.sub(r"\s*data-title=\"[^\"]*\"", "", line)
        result.append(line)
    return "\n".join(result)


def _clean_pandoc_output(text: str) -> str:
    """清理 Pandoc GFM 表格的空列和占位符"""
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        if "||" in line:
            parts = line.split("|")
            if all(p.strip() in ("", "---") for p in parts if p.strip()):
                cleaned.append(line)
                continue
            filtered = [p for p in parts if p.strip() != "" or p == parts[0] or p == parts[-1]]
            cleaned.append("|".join(filtered) if filtered else line)
        else:
            cleaned.append(line)
    return "\n".join(cleaned)


def _wikitable_to_markdown(text: str) -> str:
    """将 wikitext {| ... |} 格式直接转为 Markdown"""
    lines = text.strip().splitlines()
    if not lines:
        return ""

    result_lines = []
    header_done = False
    in_table = False

    for line in lines:
        line = line.strip()
        if line.startswith("{|"):
            in_table = True
            header_done = False
            continue
        if line == "|}" and in_table:
            in_table = False
            continue
        if not in_table:
            continue

        if line.startswith("|-"):
            continue
        if line.startswith("!"):
            cells = re.split(r"!([^![]*)", line)
            header_cells = []
            for cell in cells:
                cell = cell.strip().removesuffix("||")
                if cell:
                    header_cells.append(cell)
            if header_cells and not header_done:
                result_lines.append("| " + " | ".join(header_cells) + " |")
                result_lines.append("| " + " | ".join(["---"] * len(header_cells)) + " |")
                header_done = True
            continue
        if line.startswith("|"):
            cells = re.split(r"(?<!!)\|\|", line.lstrip("|"))
            row_cells = [c.strip() for c in cells]
            if any(row_cells):
                result_lines.append("| " + " | ".join(row_cells) + " |")

    return "\n".join(result_lines)
