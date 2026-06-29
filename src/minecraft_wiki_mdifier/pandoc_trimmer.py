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
    table = expanded.get("table", [])
    if not table:
        return expanded.get("text", "")

    lines = []
    for row in table:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")

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
    {{HistoryLine|[标志]|[版本]|[日期]|[描述...]}}
    输出：- **版本号** — 描述
    """
    params = info.get("params", info.get("text", ""))
    if isinstance(params, str):
        return _wrap_template("HistoryLine", params)

    version_label = str(params.get("1", "")).strip()
    version_num = str(params.get("2", "")).strip()
    description = str(params.get("3", "")).strip()

    for key in sorted(params.keys(), key=lambda k: (not str(k).isdigit(), k)):
        v = str(params[key]).strip()
        if v and v not in (version_label, version_num) and not v.startswith("http"):
            description = v

    meta_parts = []
    for key, value in sorted(params.items()):
        if not str(key).isdigit() and str(value).strip():
            meta_parts.append(str(value).strip())

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
        return ""

    return _wrap_template("HistoryLine", line)


def _render_history_table(info: dict, lang: str) -> str:
    """
    渲染 HistoryTable 模板为时间线格式
    每个 param value 都是 {{HistoryLine|...}} wikitext
    """
    params = info.get("params", {})
    if not params:
        return _wrap_template("HistoryTable", "")

    from minecraft_wiki_mdifier.parser import _split_template_params

    lines = []
    for key in sorted(params.keys(), key=lambda k: (not str(k).isdigit(), k)):
        value = str(params[key]).strip()
        if not value:
            continue

        if "{{HistoryLine" in value:
            inner = value.lstrip("{").rstrip("}").rstrip("{").rstrip("}")
            parts = _split_template_params(inner)
            if not parts:
                continue

            inner_params: dict[str, str] = {}
            for i, part in enumerate(parts[1:], start=1):
                part = part.strip()
                if not part:
                    continue
                if "=" in part:
                    k2, v2 = part.split("=", 1)
                    inner_params[k2.strip()] = v2.strip()
                else:
                    inner_params[str(i)] = part

            version_label = inner_params.get("1", "").strip()
            version_num = inner_params.get("2", "").strip()
            description = inner_params.get("3", "").strip()

            if not description:
                for k2 in sorted(inner_params.keys(), key=lambda x: (not x.isdigit(), x)):
                    v2 = inner_params[k2].strip()
                    if v2 and v2 not in (version_label, version_num) and not v2.startswith("http"):
                        description = v2
                        break

            meta_parts = []
            for k2, v2 in sorted(inner_params.items()):
                if not k2.isdigit() and v2.strip():
                    meta_parts.append(v2.strip())

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
    {{ID table|数字ID=256|字符串ID=minecraft:iron_ingot}}
    """
    params = info.get("params", info.get("text", ""))
    if isinstance(params, str):
        return _wrap_template("ID table", params)

    rows = []
    for key, value in sorted(params.items()):
        if str(key).isdigit():
            continue
        key_str = str(key).strip()
        value_str = str(value).strip()
        if not value_str:
            continue
        label = key_str
        kl = key_str.lower()
        if kl in ("数字id", "数字", "numeric id", "数字 id"):
            label = "数字"
        elif kl in ("字符串id", "字符串", "string id", "字符串 id"):
            label = "字符串"
        elif kl in ("物品id", "物品", "item id", "物品 id"):
            label = "物品"
        elif kl in ("方块id", "方块", "block id", "方块 id"):
            label = "方块"
        rows.append([label, value_str])

    if not rows:
        return _wrap_template("ID table", "")

    lines = ["| 类型 | 值 |", "|------|-----|"]
    for label, value in rows:
        lines.append(f"| {label} | {value} |")

    return _wrap_template("ID table", "\n".join(lines))


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
