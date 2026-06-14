"""
模板展开器

通过 MediaWiki API 展开模板，获取渲染后的HTML
"""

from collections.abc import Callable

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from mdifier.exceptions import InvalidInputError
from mdifier.formatters import MinecraftColorFormatter
from mdifier.wiki import LANG_CONFIG, USER_AGENT

# 格式检测器：(elem) -> 格式字符串 | None
# 注册表形式，按优先级顺序匹配；首个返回非 None 的获胜
FormatDetector = Callable[[object], str | None]
FORMAT_DETECTORS: list[FormatDetector] = [
    # 0. en wiki infobox：div 有 infobox class，内部有 infobox-rows table
    lambda e: (
        "infobox_table"
        if e.name == "div" and "infobox" in (e.get("class") or []) and e.find(class_="infobox-rows")
        else None
    ),
    # 1. zh wiki infobox 表格
    lambda e: "infobox_table" if e.find(class_="infobox-row") else None,
    # 2. mcui（elem 本身有 mcui class，或内部有 mcui 元素）
    #    优先于一般表格检测，确保含 mcui 单元格的 wikitable 走 mcui 分支
    lambda e: "mcui" if ("mcui" in (e.get("class") or []) or e.find(class_="mcui")) else None,
    # 3. 一般表格（elem 是 table 且内部无 mcui）
    lambda e: "table" if e.name == "table" and not e.find(class_="mcui") else None,
]


class TemplateExpander:
    """模板展开器"""

    def __init__(self, lang: str = "zh"):
        if lang not in LANG_CONFIG:
            raise InvalidInputError(
                f"Unsupported language: {lang}. Available: {list(LANG_CONFIG.keys())}"
            )
        self.lang = lang
        self.api_url = LANG_CONFIG[lang]["api"]
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist={429, 500, 502, 503, 504},
            raise_on_status=False,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))
        self.formatter = MinecraftColorFormatter()

    def expand(self, template_call: str) -> dict:
        """
        展开模板调用

        Args:
            template_call: 模板调用字符串，如 "{{Hatnote|text}}"

        Returns:
            dict: {
                "html": 渲染后的HTML,
                "class": HTML元素的class,
                "text": 提取的文本内容,
                "format": 格式类型 ("text", "infobox_table", "table"),
                "table": 表格数据（如果有的话）
            }
        """
        params = {
            "action": "parse",
            "text": template_call,
            "format": "json",
            "prop": "text",
        }
        resp = self.session.get(self.api_url, params=params)
        data = resp.json()
        html = data["parse"]["text"]["*"]

        return self._parse_expanded_html(html, template_call)

    def _parse_expanded_html(self, html: str, template_call: str | None = None) -> dict:
        """
        解析展开后的HTML，提取class和内容

        Args:
            html: 渲染后的HTML内容
            template_call: 原始模板调用字符串（如 "{{crafting usage|Iron Ingot}}"）

        Returns:
            dict: {
                "html": 原始HTML,
                "class": 主要元素的class,
                "text": 主要元素的文本内容,
                "format": 格式类型,
                "table": 表格数据（如果有的话）,
                "template_name": 语义模板名（如 "crafting usage"）
            }
        """
        soup = BeautifulSoup(html, "html.parser")

        # 找到外层容器
        container = soup.find("div", class_="mw-content-ltr")
        if container is None:
            container = soup

        # 在容器内找第一个真正的模板元素（不是 mw-parser-output）
        elem = container.find(class_=lambda c: c and "mw-parser-output" not in c)

        # 提取 history-json pre 数据（在移除前，en wiki 元数据块）
        infobox_json = None
        for pre in soup.find_all("pre", class_=lambda c: c and "history-json" in c):
            try:
                import json

                infobox_json = json.loads(pre.get_text(strip=True))
            except Exception:
                pass
            pre.decompose()

        # 从 template_call 提取语义名称
        template_name = None
        if template_call:
            name_part = template_call.lstrip("{").rstrip("}").split("|")[0].strip()
            if ":" in name_part:
                name_part = name_part.split(":", 1)[1]
            template_name = name_part

        if elem is None:
            # 如果没找到，返回整个HTML
            return {
                "html": html,
                "class": None,
                "text": soup.get_text(strip=True),
                "format": "text",
                "table": None,
                "template_name": template_name,
            }

        classes = elem.get("class", [])
        main_class = classes[0] if classes else None

        # 检测格式
        fmt = self._detect_format(elem)

        result = {
            "html": str(elem),
            "class": main_class,
            "text": elem.get_text(strip=True),
            "format": fmt,
            "table": None,
            "template_name": template_name,
        }

        # 解析表格
        if fmt in ("infobox_table", "table", "mcui"):
            result["table"] = self._parse_table(elem, fmt, infobox_json)

        return result

    def _detect_format(self, elem) -> str:
        """
        检测HTML格式类型

        Args:
            elem: BeautifulSoup元素

        Returns:
            格式类型: "text", "infobox_table", "table", "mcui"
        """
        for detector in FORMAT_DETECTORS:
            fmt = detector(elem)
            if fmt:
                return fmt
        return "text"

    def _parse_table(self, elem, fmt: str, infobox_json: dict | None = None) -> list[list[str]]:
        """
        解析HTML表格

        Args:
            elem: BeautifulSoup元素
            fmt: 格式类型
            infobox_json: en wiki history-json 数据（可选）

        Returns:
            表格数据，每行是字符串列表
        """
        rows = []

        if fmt == "infobox_table":
            # zh wiki：infobox-row div 结构
            infobox_rows = elem.find_all(class_="infobox-row")
            if infobox_rows:
                for row in infobox_rows:
                    label = row.find(class_="infobox-row-label")
                    field = row.find(class_="infobox-row-field")
                    label_text = label.get_text(strip=True) if label else ""
                    field_text = field.get_text(strip=True) if field else ""
                    rows.append([label_text, field_text])
            else:
                # en wiki：infobox-rows table + history-json pre 结构
                if infobox_json:
                    # 从 JSON 提取数据（field 是 HTML，需转换）
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
                    # 降级：解析 infobox-rows table（表格只有 "?" 占位符时）
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
            # mcui 格式（合成台/熔炉/织布机/锻造台）
            elem_classes = elem.get("class") or []
            if "mcui" in elem_classes:
                # elem 本身就是 mcui，整体单格
                text = self._parse_mcui(elem)
                rows.append([text])
            else:
                # elem 是 table，内部有 mcui 单元格，保留完整行结构
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
                    # 没有 table 结构，降级为单个 mcui
                    for mcui in elem.find_all(class_="mcui"):
                        text = self._parse_mcui(mcui)
                        rows.append([text])
        else:
            # 一般表格：解析HTML table
            # elem可能是 table 或包含 table 的容器
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
                            text = cell.get_text(separator=" ", strip=True)
                        cells.append(text)
                    if cells:
                        rows.append(cells)

        return rows

    def _parse_mcui(self, mcui) -> str:
        """
        解析 mcui 结构，输出语义化文本

        Args:
            mcui: BeautifulSoup mcui 元素

        Returns:
            格式化的物品信息字符串
        """
        parts = []

        # 通过 mcui 的 class 区分类型
        mcui_classes = mcui.get("class") or []
        is_furnace = any("Furnace" in cls for cls in mcui_classes)
        is_smithing = any("Smithing" in cls for cls in mcui_classes)

        # 收集所有输入槽位
        inputs = []

        if is_smithing:
            # Smithing: 多个 invslot 直接挂在 mcui 下，没有 mcui-input 包装
            slots = self._collect_smithing_inputs(mcui)
            if slots:
                inputs.append(" + ".join(slots))
        else:
            # 合成/熔炉/Loom
            mcui_input = mcui.find(class_="mcui-input")
            if mcui_input:
                if is_furnace:
                    inputs.append(self._parse_furnace_input(mcui_input))
                elif mcui_input.find(class_="mcui-row"):
                    inputs.append(self._parse_grid_input(mcui_input))
                else:
                    inputs.append(self._parse_single_input(mcui_input))

            # mcui-inputPattern (Loom 特殊命名)
            mcui_input_pattern = mcui.find(class_="mcui-inputPattern")
            if mcui_input_pattern:
                pattern = self._parse_single_input(mcui_input_pattern)
                if pattern:
                    inputs.append(pattern)

        inputs = [s for s in inputs if s]
        if inputs:
            parts.append(" ".join(inputs))

        # 输出：smithing 的输出 invslot 也在 mcui 直接子级
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
                # 跳过输出槽（通过 style="margin-left: 72px" 区分）
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
        """
        3x3 网格输入：每行独立，用 | 分隔单元格，/ 分隔行
        [[|]] searchaux 标记代表空位置
        """
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
                    # 隐藏 [[|]] 标记：代表空位置
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
                continue  # 跳过 [[|]] 隐藏标记
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
        # 优先用 invslot-item 直接的 title 属性（zh wiki 风格）
        # 降级：在嵌套的 <a title="..."> 中查找（en wiki 风格）
        title = item.get("title")
        if not title:
            link = item.find("a", title=True)
            title = link.get("title") if link else None
        title = self.formatter.clean(title) if title else "?"

        # 查找所在 invslot 的 stacksize
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
