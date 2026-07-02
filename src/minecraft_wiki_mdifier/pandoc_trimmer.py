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
from urllib.parse import unquote

import pypandoc
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from minecraft_wiki_mdifier.template_expander import TemplateExpander
from minecraft_wiki_mdifier.wiki import LANG_CONFIG

# =============================================================================
# 辅助函数
# =============================================================================


def _get_english_title(chinese_title: str, lang: str) -> str | None:
    """
    通过 langlinks API 获取页面的英文名称

    Args:
        chinese_title: 中文页面标题
        lang: 语言代码

    Returns:
        英文标题，或 None（查询失败时）
    """
    if lang != "zh":
        return None

    api_url = LANG_CONFIG["zh"]["api"]
    params = {
        "action": "query",
        "titles": chinese_title,
        "prop": "langlinks",
        "lllang": "en",
        "format": "json",
    }
    try:
        resp = requests.post(api_url, data=params, timeout=10)
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            langlinks = page.get("langlinks", [])
            for link in langlinks:
                if link.get("lang") == "en":
                    return link.get("*")
    except Exception:
        pass
    return None


def _has_table_data(expanded: dict) -> bool:
    """检测展开结果是否包含实际表格数据（而非只有表头）"""
    # 检查 HTML 中是否有 <td> 元素（数据单元格）来判断是否有真实数据
    html = expanded.get("html", "")
    if html and "<td" in html:
        return True
    # 回退：检查 table 是否有足够多行
    table = expanded.get("table", [])
    if table and len(table) > 2:
        return True
    return False


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

# 匹配引用标记 <sup class="reference">...</sup>
_CITE_BRACKET_PATTERN = re.compile(
    r'<sup[^>]*class="reference"[^>]*>.*?</sup>',
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
    "drop sources": "_render_table_grid",
    "lootchestitem": "_render_table_grid",
    "trade uses": "_render_table_grid",
    "droptable": "_render_droptable",
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

            # Trade uses 空表格修复：尝试注入英文参数重试
            tmpl_name = expanded.get("template_name", "").lower()
            if tmpl_name == "trade uses" and not _has_table_data(expanded):
                english_name = _get_english_title(page_title, lang)
                if english_name:
                    retried = expander.expand(f"{{{{Trade uses|{english_name}}}}}", page_title)
                    if _has_table_data(retried):
                        return _render_template_to_markdown(retried, lang)

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

            # Trade uses 空表格修复（内联模板同理）
            tmpl_name = expanded.get("template_name", "").lower()
            if tmpl_name == "trade uses" and not _has_table_data(expanded):
                english_name = _get_english_title(page_title, lang)
                if english_name:
                    retried = expander.expand(f"{{{{Trade uses|{english_name}}}}}", page_title)
                    if _has_table_data(retried):
                        return _render_template_to_markdown(retried, lang)

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
        """格式化单元格：转义 | 和换行"""
        return str(cell).replace("\n", "<br/>").replace("|", "\\|")

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


def _get_cell_text(td) -> str:
    """获取单元格的纯文本，移除引用标记"""
    html = str(td)
    html = _CITE_BRACKET_PATTERN.sub("", html)
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" / ", strip=True)


def _render_table_grid(expanded: dict, lang: str) -> str:
    """
    统一渲染表格，支持 rowspan 和 colspan 同时存在

    算法：虚拟网格放置法
    - 多行表头：合并为展平的列定义
    - 数据行：按 col_state 跳过被 rowspan 占据的列
    - colspan > 1 的单元格占用多个列位置
    """
    html = expanded.get("html", "")
    if not html:
        return expanded.get("text", "")

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return _render_html_generic(expanded, lang)

    # 1. 解析所有行（BeautifulSoup 元素）
    all_trs = table.find_all("tr")
    if not all_trs:
        return _render_html_generic(expanded, lang)

    # 2. 分离表头行和数据行
    header_trs = []
    data_trs = []
    for tr in all_trs:
        ths = tr.find_all("th")
        tds = tr.find_all("td")
        if ths and not tds:
            header_trs.append(ths)
        elif tds:
            data_trs.append(tds)

    if not header_trs:
        return _render_html_generic(expanded, lang)

    # 3. 建立列定义
    col_defs = _build_col_defs(header_trs)

    # 4. 渲染数据行
    col_state = {}  # col_index -> (text, remaining_rows)
    rendered_rows = []

    for tds in data_trs:
        row_cells = []
        for td in tds:
            row_cells.append(
                {
                    "text": _get_cell_text(td),
                    "colspan": int(td.get("colspan", 1)),
                    "rowspan": int(td.get("rowspan", 1)),
                }
            )
        rendered_row, col_state = _place_row_cells(row_cells, col_defs, col_state)
        rendered_rows.append(rendered_row)

    # 5. 生成 Markdown
    lines = []
    header_cells = [d["text"] for d in col_defs]
    lines.append("| " + " | ".join(header_cells) + " |")
    lines.append("| " + " | ".join(["---"] * len(col_defs)) + " |")

    for row in rendered_rows:
        cells = [c.replace("\n", "<br/>").replace("|", "\\|") for c in row]
        lines.append("| " + " | ".join(cells) + " |")

    name = expanded.get("template_name") or expanded.get("class")
    if not name:
        return "\n".join(lines)
    return _wrap_template(name, "\n".join(lines))


# HTML 引用脚注提取正则：提取 cite_note-xxx-N 对应的脚注文本
_DROPTABLE_REF_PATTERN = re.compile(
    r'<li id="cite_note-([^"]+)"[^>]*>.*?<span class="reference-text">(.*?)</span>',
    re.DOTALL,
)


def _render_droptable(expanded: dict, lang: str) -> str:
    """
    渲染 DropTable 模板为 Markdown，同时保留掉落注释脚注。

    action=parse 返回的 HTML 中，droptable-references div 包含脚注内容。
    我们先用 markdownify 渲染表格 HTML，再提取脚注并生成 Markdown 脚注。
    """
    # 优先使用 raw_html（含 references div），否则降级到 html
    html = expanded.get("raw_html") or expanded.get("html", "")

    # 提取脚注：key → label + text
    # 注意：raw_html 包含多个版本（Java/Bedrock）的 DropTable，
    # 但脚注内容相同，只保留 base_key（如 random_disc）去重
    footnotes: dict[str, tuple[str, str]] = {}  # cite_key → (label, text)
    seen_base: set[str] = set()  # 记录已处理的 base_key（如 random_disc）
    for m in _DROPTABLE_REF_PATTERN.finditer(html):
        cite_key = m.group(1)  # 如 random_disc-1
        raw_text = m.group(2).strip()
        # 解码 HTML 实体
        text_soup = BeautifulSoup(raw_text, "html.parser")
        text = text_soup.get_text(separator=" ", strip=True)
        # base_key = cite_key 去掉尾部序号（如 random_disc-1 → random_disc）
        parts = cite_key.rsplit("-", 1)
        base_key = parts[0] if len(parts) == 2 and parts[1].isdigit() else cite_key
        if base_key not in seen_base:
            seen_base.add(base_key)
            footnotes[cite_key] = (chr(64 + len(footnotes) + 1), text)

    # 用 markdownify 渲染 tabber div（去除 references 避免干扰）
    soup = BeautifulSoup(html, "html.parser")
    for ref_div in soup.find_all("div", class_="droptable-references"):
        ref_div.decompose()
    for style in soup.find_all("style"):
        style.decompose()

    # 移除 sprite-file span（干扰 markdownify）
    html_clean = _SPRITE_FILE_PATTERN.sub("", str(soup))
    rendered = md(html_clean, heading_style="atx", bullet_char="-")

    # 替换相对路径
    static_base = LANG_CONFIG[lang]["static_base"]
    rendered = rendered.replace("/images/", f"{static_base}/images/")
    rendered = rendered.replace("/w/", f"{static_base}/w/")
    rendered = unquote(rendered)

    # 转换 Pandoc 风格的 [[A]](cite_note-xxx) 或 [A](cite_note-xxx) 为 [^A]
    def replace_ref(m):
        # m.group(1) 是链接文本（如 A），m.group(2) 是 cite_key（如 random_disc-1）
        cite_id = m.group(2)
        parts = cite_id.rsplit("-", 1)
        base_key = parts[0] if len(parts) == 2 and parts[1].isdigit() else cite_id
        # 查找 base_key 对应的 label
        for key, (label, _) in footnotes.items():
            if key.startswith(base_key):
                return f"[^{label}]"
        return m.group(0)  # 未找到则保留原样

    # 支持 [[A]](cite_note-xxx) 和 [A](cite_note-xxx) 两种格式
    rendered = re.sub(r"\[+([^\]]*?)\]+\(#cite_note-([^)]+)\)", replace_ref, rendered)

    # 生成脚注
    footnote_lines = []
    for _cite_key, (label, text) in footnotes.items():
        footnote_lines.append(f"[^{label}]: {text}")

    if footnote_lines:
        rendered = rendered.rstrip() + "\n\n" + "\n".join(footnote_lines) + "\n"

    name = expanded.get("template_name") or expanded.get("class")
    if name:
        rendered = _wrap_template(name, rendered)

    return rendered


def _build_col_defs(header_trs) -> list[dict]:
    """
    从多行表头构建列定义

    算法：
    - 遍历每一行（非最后一行），按 colspan 展开为 N 个列
    - 每个展开后的列使用子行中对应的标签
    - rowspan>1 作为 1 列（后续行显示空）
    """
    if len(header_trs) == 1:
        # 单行表头
        col_defs = []
        for th in header_trs[0]:
            text = th.get_text(strip=True)
            col_defs.append({"text": text})
        return col_defs

    # 多行表头：建立列定义
    # 子行标签（最后一行）提供每个实际列的标签
    last_row = header_trs[-1]
    sub_labels = [th.get_text(strip=True) for th in last_row]

    col_defs = []
    sub_idx = 0

    for row in header_trs[:-1]:
        for th in row:
            rowspan = int(th.get("rowspan", 1))
            colspan = int(th.get("colspan", 1))
            parent_text = th.get_text(strip=True)

            if rowspan > 1:
                # rowspan>1：作为 1 列（后续行显示空）
                col_defs.append({"text": parent_text})
                sub_idx += 1  # 占据子行中的 1 列
                continue

            if colspan > 1:
                # colspan>1：展开为 N 个列，每个使用子行的对应标签
                for _ in range(colspan):
                    sub_text = sub_labels[sub_idx] if sub_idx < len(sub_labels) else ""
                    sub_idx += 1
                    if sub_text:
                        col_defs.append({"text": f"{parent_text}({sub_text})"})
                    else:
                        col_defs.append({"text": parent_text})
            else:
                sub_text = sub_labels[sub_idx] if sub_idx < len(sub_labels) else ""
                sub_idx += 1
                if sub_text:
                    col_defs.append({"text": f"{parent_text}({sub_text})"})
                else:
                    col_defs.append({"text": parent_text})

    return col_defs


def _place_row_cells(row_cells: list, col_defs: list, col_state: dict) -> tuple[list[str], dict]:
    """
    将数据单元格放置到网格中

    1. 从左到右扫描，按 col_state 跳过被 rowspan 占据的列
    2. 将单元格按 colspan 占据多个列
    3. 每行结束后统一缩减所有 rowspan remaining
    """
    num_cols = len(col_defs)
    placed = [""] * num_cols
    col_idx = 0
    cell_idx = 0

    while col_idx < num_cols and cell_idx < len(row_cells):
        if col_idx in col_state:
            # 该列被 rowspan 占据，跳过
            col_idx += 1
            continue

        cell = row_cells[cell_idx]
        cell_idx += 1

        # 先检查并跳过所有被占据的列
        while col_idx < num_cols and col_idx in col_state:
            col_idx += 1
        if col_idx >= num_cols:
            break

        # 占据 colspan 个列
        for offset in range(cell["colspan"]):
            if col_idx + offset >= num_cols:
                break
            # offset == 0 时放置文本，offset > 0 时留空
            placed[col_idx + offset] = cell["text"] if offset == 0 else ""

        # 更新 col_state：标记所有被占据的列（remaining 不在这里缩减）
        if cell["rowspan"] > 1:
            for c in range(col_idx, min(col_idx + cell["colspan"], num_cols)):
                col_state[c] = (cell["text"], cell["rowspan"] - 1)
        col_idx += cell["colspan"]

    # 每行结束后，统一缩减所有 rowspan remaining
    new_state = {}
    for c, (text, remaining) in col_state.items():
        if remaining >= 1:
            new_state[c] = (text, remaining - 1)
    col_state = new_state

    return placed, col_state


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

    # 解码 URL 中的百分号编码（如 %E9%93%81 -> 铁）
    rendered = unquote(rendered)

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
        """格式化单元格：转义 | 和换行"""
        return str(cell).replace("\n", "<br/>").replace("|", "\\|")

    lines = []
    for row in table:
        lines.append("| " + " | ".join(format_cell(cell) for cell in row) + " |")

    if len(table) > 0:
        col_count = len(table[0])
        lines.insert(1, "| " + " | ".join(["---"] * col_count) + " |")

    return _wrap_template("ID table", "\n".join(lines))


def _render_navbox_items(info: dict, lang: str) -> str:
    """
    渲染 Navbox items 模板为分类列表格式
    保留 HTML 中的分类层级结构
    """
    html = info.get("html", "")
    if not html:
        text = info.get("text", "")
        return _wrap_template("Navbox items", text) if text else ""

    soup = BeautifulSoup(html, "html.parser")
    navbox = soup.find("table", class_="navbox")

    # 如果有 navbox 表格，提取分类结构
    if navbox:
        lines = []
        current_category = ""

        for elem in navbox.find_all(["th", "li"]):
            th_class = elem.get("class", [])
            text = elem.get_text(strip=True)
            if not text:
                continue
            if "navbox-top" in th_class:
                continue
            elif "navbox-middle" in th_class:
                if current_category and lines:
                    lines.append("")
                lines.append(f"**{text}**")
                current_category = text
            elif th_class and "navbox-middle" not in th_class and elem.name == "th":
                lines.append(f"*{text}*")
            elif elem.name == "li":
                # 跳过 Wikipedia 标准顶级导航链接（查/论/编等单字）
                if len(text) <= 2 and text in (
                    "查",
                    "论",
                    "编",
                    "阅",
                    "历",
                    "View",
                    "Discuss",
                    "Edit",
                ):
                    continue
                lines.append(f"- {text}")

        if lines:
            return _wrap_template("Navbox items", "\n".join(lines))

    # 处理简单的 ul/li 结构（测试用例兼容）
    ul = soup.find("ul")
    if ul:
        items = []
        for li in ul.find_all("li"):
            text = li.get_text(strip=True)
            if text:
                items.append(f"- {text}")
        if items:
            return _wrap_template("Navbox items", "\n".join(items))

    # Fallback: 用 markdownify 处理
    return _render_html_generic(info, lang)

    lines = []
    current_category = ""

    def process_element(elem):
        """递归处理元素，返回 (is_heading, text) 元组"""
        tag = elem.name
        if tag == "th":
            th_class = elem.get("class", [])
            text = elem.get_text(strip=True)
            if "navbox-top" in th_class:
                # 导航栏标题，跳过
                return False, None
            elif "navbox-middle" in th_class:
                # 一级分类
                return True, ("category", text)
            else:
                # 二级分类标题
                return True, ("subcategory", text)
        elif tag == "li":
            text = elem.get_text(strip=True)
            return True, ("item", text)
        return False, None

    # 收集所有 th 和 li（保持文档顺序）
    elements = []
    for elem in navbox.find_all(["th", "li"]):
        is_valid, data = process_element(elem)
        if is_valid and data:
            elements.append(data)

    # 转换为行
    for elem_type, text in elements:
        if elem_type == "category":
            if current_category and lines:
                lines.append("")
            lines.append(f"**{text}**")
            current_category = text
        elif elem_type == "subcategory":
            lines.append(f"*{text}*")
        elif elem_type == "item":
            lines.append(f"- {text}")

    if not lines:
        return _render_html_generic(info, lang)

    return _wrap_template("Navbox items", "\n".join(lines))


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
    # 简化 interwiki 链接：[cs:Title](cs:Title) → [cs:Title]
    # 简化 interwiki 链接并补全为完整 URL
    # [cs:Železný ingot](cs:Železný_ingot) → [cs:Železný ingot](https://cs.minecraft.wiki/Železný_ingot)
    text = re.sub(
        r"\[([a-z]{2,3}):([^\]]+)\]\([a-z]{2,3}:([^\)]+)\)",
        lambda m: f"[{m.group(1)}:{m.group(2)}](https://{m.group(1)}.minecraft.wiki/{m.group(3)})",
        text,
    )
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
