"""
模板展开器

通过 MediaWiki API 展开模板，获取渲染后的HTML
"""

from __future__ import annotations

import base64
import logging
import threading
from collections.abc import Callable

import requests  # noqa: F401
from bs4 import BeautifulSoup

from minecraft_wiki_mdifier._session import create_session
from minecraft_wiki_mdifier._validators import validate_lang
from minecraft_wiki_mdifier.formatters import MinecraftColorFormatter
from minecraft_wiki_mdifier.wiki import LANG_CONFIG

_logger = logging.getLogger(__name__)


def _encode_cache_value(v: str) -> str:
    """URL-safe base64 编码，避免分隔符冲突。"""
    return base64.urlsafe_b64encode(v.encode("utf-8")).decode("ascii")


# 格式检测器：(elem) -> 格式字符串 | None
FormatDetector = Callable[[object], str | None]
FORMAT_DETECTORS: list[FormatDetector] = [
    # 1. zh wiki infobox 表格
    lambda e: "infobox_table" if e.find(class_="infobox-row") else None,
    # 2. mcui（elem 本身有 mcui class，或内部有 mcui 元素）
    lambda e: "mcui" if ("mcui" in (e.get("class") or []) or e.find(class_="mcui")) else None,
    # 3. 一般表格（elem 是 table 且内部无 mcui）
    lambda e: "table" if e.name == "table" and not e.find(class_="mcui") else None,
]


class TemplateExpander:
    """模板展开器"""

    def __init__(
        self,
        lang: str = "zh",
        template_cache: dict | None = None,
        cache_lock: threading.Lock | None = None,
    ):
        validate_lang(lang)
        self.lang = lang
        self.api_url = LANG_CONFIG[lang]["api"]
        self.session = create_session()
        self.formatter = MinecraftColorFormatter()
        self._template_cache = template_cache if template_cache is not None else {}
        self._cache_lock = cache_lock if cache_lock is not None else threading.Lock()

    def expand(self, template_call: str, page_title: str | None = None) -> dict:
        """
        展开模板调用

        Args:
            template_call: 模板调用字符串，如 "{{Hatnote|text}}"
            page_title: 页面标题（用于解析上下文）

        Returns:
            dict: {
                "html": 渲染后的HTML,
                "class": HTML元素的class,
                "text": 提取的文本内容,
                "format": 格式类型 ("text", "infobox_table", "table", "mcui"),
                "table": 表格数据（如果有的话）
            }
        """
        cache_key = _encode_cache_value(template_call)
        with self._cache_lock:
            if cache_key in self._template_cache:
                return self._template_cache[cache_key]
        result = self._expand_via_parse(template_call)
        with self._cache_lock:
            self._template_cache[cache_key] = result
        return result

    def _expand_via_parse(self, template_call: str) -> dict:
        """
        通过 action=parse API 展开模板
        支持 variant 参数，可正确处理 zh-cn/zh-tw/zh-hk 语言变体

        Args:
            template_call: 模板调用字符串

        Returns:
            标准展开结果 dict
        """
        # zh wiki 需要 variant 参数剥离语言变体标记
        variant = self.lang if self.lang in ("en", "ja") else "zh-cn"
        params = {
            "action": "parse",
            "text": template_call,
            "format": "json",
            "prop": "text",
            "variant": variant,
        }
        resp = self.session.post(self.api_url, data=params, timeout=30)
        data = resp.json()
        html = data["parse"]["text"]["*"]

        return self._parse_expanded_html(html, template_call)

    def _parse_expanded_html(self, html: str, template_call: str | None = None) -> dict:
        """
        解析展开后的HTML，提取class和内容

        Args:
            html: 渲染后的HTML内容
            template_call: 原始模板调用字符串

        Returns:
            dict: {
                "html": 原始HTML,
                "class": 主要元素的class,
                "text": 主要元素的文本内容,
                "format": 格式类型,
                "table": 表格数据（如果有的话）,
                "template_name": 语义模板名
            }
        """
        soup = BeautifulSoup(html, "html.parser")

        container = soup.find("div", class_="mw-content-ltr")
        if container is None:
            container = soup

        elem = container.find(class_=lambda c: c and "mw-parser-output" not in c)

        # 提取 history-json pre 数据（en wiki 元数据块）
        infobox_json = None
        for pre in soup.find_all("pre", class_=lambda c: c and "history-json" in c):
            try:
                import json

                infobox_json = json.loads(pre.get_text(strip=True))
            except json.JSONDecodeError as e:
                _logger.debug("infobox_json decode failed: %s", e)

        # 从 template_call 提取语义名称
        template_name = None
        if template_call:
            name_part = template_call.lstrip("{").rstrip("}").split("|")[0].strip()
            if ":" in name_part:
                name_part = name_part.split(":", 1)[1]
            template_name = name_part

        if elem is None:
            return {
                "html": html,
                "raw_html": html,
                "class": None,
                "text": soup.get_text(strip=True),
                "format": "text",
                "table": None,
                "template_name": template_name,
            }

        classes = elem.get("class", [])
        main_class = classes[0] if classes else None

        fmt = self._detect_format(elem, infobox_json)

        result = {
            "html": str(elem),
            "class": main_class,
            "text": elem.get_text(strip=True),
            "format": fmt,
            "table": None,
            "template_name": template_name,
        }

        # 对于 DropTable 等特殊模板，保留完整 HTML（含脚注 references）
        # container 可能比 elem（tabber div）更外层，包含 droptable-references
        if container and str(container) != str(elem):
            result["raw_html"] = str(container)

        if fmt in ("infobox_table", "table", "mcui"):
            result["table"] = self._parse_table(elem, fmt, infobox_json)

        if fmt == "infobox_table":
            for pre in soup.find_all("pre", class_=lambda c: c and "history-json" in c):
                pre.decompose()

        return result

    def _detect_format(self, elem, infobox_json: dict | None = None) -> str:
        """检测HTML格式类型"""
        if infobox_json is not None and elem.find(class_="infobox-rows"):
            return "infobox_table"
        for detector in FORMAT_DETECTORS:
            fmt = detector(elem)
            if fmt:
                return fmt
        return "text"

    def _parse_table(self, elem, fmt: str, infobox_json: dict | None = None) -> list[list[str]]:
        """解析HTML表格"""
        rows = []

        if fmt == "infobox_table":
            infobox_rows = elem.find_all(class_="infobox-row")
            if infobox_rows:
                for row in infobox_rows:
                    label = row.find(class_="infobox-row-label")
                    field = row.find(class_="infobox-row-field")
                    label_text = label.get_text(strip=True) if label else ""
                    field_text = field.get_text(strip=True) if field else ""
                    rows.append([label_text, field_text])
            else:
                if infobox_json:
                    from bs4 import BeautifulSoup as BS

                    for entry in infobox_json.get("rows", []):
                        field_html = entry.get("field", "")
                        if field_html:
                            field_text = BS(field_html, "html.parser").get_text(
                                separator=" ", strip=True
                            )
                        else:
                            field_text = entry.get("field_plain", "")
                        label_text = entry.get("label", "")
                        rows.append([label_text, field_text])
                else:
                    table = elem.find("table", class_=lambda c: c and "infobox-rows" in c)
                    if table:
                        for tr in table.find_all("tr"):
                            ths = tr.find_all("th")
                            tds = tr.find_all("td")
                            if ths and tds:
                                label_text = ths[0].get_text(strip=True)
                                field_text = tds[0].get_text(strip=True)
                                rows.append([label_text, field_text])
        elif fmt == "mcui":
            elem_classes = elem.get("class") or []
            if "mcui" in elem_classes:
                text = self._parse_mcui(elem)
                rows.append([text])
            else:
                table = elem if elem.name == "table" else elem.find("table")
                if table:
                    for tr in table.find_all("tr"):
                        cells = []
                        for cell in tr.find_all(["th", "td"]):
                            mcui = cell.find(class_="mcui")
                            if mcui:
                                cells.append(self._parse_mcui(mcui))
                            else:
                                cells.append(cell.get_text(separator=" ", strip=True))
                        if cells:
                            rows.append(cells)
                else:
                    for mcui in elem.find_all(class_="mcui"):
                        text = self._parse_mcui(mcui)
                        rows.append([text])
        else:
            table = elem if elem.name == "table" else elem.find("table")
            if table:
                for tr in table.find_all("tr"):
                    raw_ths = tr.find_all("th")
                    raw_tds = tr.find_all("td")
                    cells = []
                    for cell in raw_ths + raw_tds:
                        mcui = cell.find(class_="mcui")
                        if mcui:
                            text = self._parse_mcui(mcui)
                        else:
                            # 用换行符连接 <br/> 分隔的内容
                            text = cell.get_text(separator="\n", strip=True)
                        cells.append(text)
                    if cells:
                        rows.append(cells)

        return rows

    def _parse_mcui(self, mcui) -> str:
        """解析 mcui 结构，输出语义化文本"""
        parts = []

        mcui_classes = mcui.get("class") or []
        is_furnace = any("Furnace" in cls for cls in mcui_classes)
        is_smithing = any("Smithing" in cls for cls in mcui_classes)

        inputs = []

        if is_smithing:
            slots = self._collect_smithing_inputs(mcui)
            if slots:
                inputs.append(" + ".join(slots))
        else:
            mcui_input = mcui.find(class_="mcui-input")
            if mcui_input:
                if is_furnace:
                    inputs.append(self._parse_furnace_input(mcui_input))
                elif mcui_input.find(class_="mcui-row"):
                    inputs.append(self._parse_grid_input(mcui_input))
                else:
                    inputs.append(self._parse_single_input(mcui_input))

            mcui_input_pattern = mcui.find(class_="mcui-inputPattern")
            if mcui_input_pattern:
                pattern = self._parse_single_input(mcui_input_pattern)
                if pattern:
                    inputs.append(pattern)

        inputs = [s for s in inputs if s]
        if inputs:
            parts.append(" ".join(inputs))

        if is_smithing:
            output_text = self._collect_smithing_output(mcui)
            if output_text:
                parts.append(f"-> {output_text}")
        else:
            mcui_output = mcui.find(class_="mcui-output")
            if mcui_output:
                output = self._parse_output(mcui_output)
                if output:
                    parts.append(f"-> {output}")

        return " ".join(parts) if parts else "?"

    def _parse_single_input(self, container) -> str:
        """解析单个输入槽位"""
        items = container.find_all(class_="invslot-item")
        if not items:
            return ""
        return "/".join(self._format_item(i) for i in items)

    def _collect_smithing_inputs(self, mcui) -> list[str]:
        """Smithing 模板：invslot 在 template-Smithing_Table-slots 下"""
        slots_container = mcui.find(class_="template-Smithing_Table-slots")
        if not slots_container:
            return []
        result = []
        for child in slots_container.children:
            if not hasattr(child, "get") or not child.get("class"):
                continue
            cls = child.get("class") or []
            if "searchaux" in cls:
                continue
            if "invslot" in cls:
                style = child.get("style", "")
                if "margin-left" in style:
                    continue
                item = child.find(class_="invslot-item")
                if item:
                    result.append(self._format_item(item))
        return result

    def _collect_smithing_output(self, mcui) -> str:
        """Smithing 模板的输出：通过 style="margin-left: 72px" 标识"""
        slots_container = mcui.find(class_="template-Smithing_Table-slots")
        if not slots_container:
            return ""
        for child in slots_container.children:
            if not hasattr(child, "get") or not child.get("class"):
                continue
            cls = child.get("class") or []
            if "invslot" in cls:
                style = child.get("style", "")
                if "margin-left" in style:
                    item = child.find(class_="invslot-item")
                    if item:
                        title = self.formatter.clean(item.get("title", "?"))
                        return title
        return ""

    def _parse_grid_input(self, mcui_input) -> str:
        """3x3 网格输入：每行独立，用 | 分隔单元格，/ 分隔行"""
        rows_text = []
        for row in mcui_input.find_all(class_="mcui-row"):
            cells = []
            for child in row.children:
                if not hasattr(child, "get"):
                    continue
                cls = child.get("class") or []
                if not cls:
                    continue
                if "searchaux" in cls:
                    cells.append("_")
                elif "invslot" in cls:
                    items = child.find_all(class_="invslot-item")
                    if items:
                        cell_text = "/".join(self._format_item(i) for i in items)
                        cells.append(cell_text)
                    else:
                        cells.append("_")
            rows_text.append("|".join(cells))
        return "[" + " / ".join(rows_text) + "]"

    def _parse_furnace_input(self, mcui_input) -> str:
        """熔炉输入：物品 + 燃料"""
        parts = []
        for child in mcui_input.children:
            if not hasattr(child, "get"):
                continue
            cls = child.get("class") or []
            if not cls:
                continue
            if "searchaux" in cls:
                continue
            elif "mcui-fuel" in cls:
                parts.append("+ 任意燃料")
            elif "invslot" in cls:
                items = child.find_all(class_="invslot-item")
                if items:
                    titles = "/".join(self._format_item(i) for i in items)
                    parts.append(titles)
        return " ".join(parts)

    def _format_item(self, item) -> str:
        """格式化单个物品（含数量）"""
        title = item.get("title")
        if not title:
            link = item.find("a", title=True)
            title = link.get("title") if link else None
        title = self.formatter.clean(title) if title else "?"

        parent = item.find_parent(class_="invslot")
        if parent:
            ss = parent.find(class_="invslot-stacksize")
            if ss:
                count = ss.get_text(strip=True)
                return f"{title}x{count}"
        return title

    def _parse_output(self, mcui_output) -> str:
        """输出物品"""
        for child in mcui_output.children:
            if not (hasattr(child, "get") and child.get("class")):
                continue
            cls = child.get("class") or []
            if "searchaux" in cls:
                continue
            elif "invslot" in cls:
                item = child.find(class_="invslot-item")
                if item:
                    title = item.get("title")
                    if not title:
                        link = item.find("a", title=True)
                        title = link.get("title") if link else None
                    title = self.formatter.clean(title) if title else "?"
                    ss = child.find(class_="invslot-stacksize")
                    count = f"x{ss.get_text()}" if ss else ""
                    return f"{title}{count}"
        return ""
