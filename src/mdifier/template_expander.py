"""
模板展开器

通过 MediaWiki API 展开模板，获取渲染后的HTML
"""

from collections.abc import Callable

import requests
from bs4 import BeautifulSoup

from mdifier.formatters import MinecraftColorFormatter
from mdifier.wiki import LANG_CONFIG

# 格式检测器：(elem) -> 格式字符串 | None
# 注册表形式，按优先级顺序匹配；首个返回非 None 的获胜
FormatDetector = Callable[[object], str | None]
FORMAT_DETECTORS: list[FormatDetector] = [
    # 1. infobox 表格
    lambda e: "infobox_table" if e.find(class_='infobox-row') else None,
    # 2. mcui（elem 本身或内部）
    lambda e: "mcui" if "mcui" in (e.get('class') or []) or e.find(class_='mcui') else None,
    # 3. 一般表格（elem 本身是 table 或内部有 table）
    lambda e: "table" if e.name == 'table' or e.find('table') else None,
]


class TemplateExpander:
    """模板展开器"""

    def __init__(self, lang: str = "zh"):
        if lang not in LANG_CONFIG:
            raise ValueError(
                f"Unsupported language: {lang}. "
                f"Available: {list(LANG_CONFIG.keys())}"
            )
        self.lang = lang
        self.api_url = LANG_CONFIG[lang]["api"]
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Minecraft-Wiki-MDifier/0.1.0 (Python Wiki Converter)"
        })
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

        return self._parse_expanded_html(html)

    def _parse_expanded_html(self, html: str) -> dict:
        """
        解析展开后的HTML，提取class和内容

        Args:
            html: 渲染后的HTML内容

        Returns:
            dict: {
                "html": 原始HTML,
                "class": 主要元素的class,
                "text": 主要元素的文本内容,
                "format": 格式类型,
                "table": 表格数据（如果有的话）
            }
        """
        soup = BeautifulSoup(html, 'html.parser')

        # 找到外层容器
        container = soup.find('div', class_='mw-content-ltr')
        if container is None:
            container = soup

        # 在容器内找第一个真正的模板元素（不是 mw-parser-output）
        elem = container.find(class_=lambda c: c and 'mw-parser-output' not in c)

        if elem is None:
            # 如果没找到，返回整个HTML
            return {
                "html": html,
                "class": None,
                "text": soup.get_text(strip=True),
                "format": "text",
                "table": None
            }

        classes = elem.get('class', [])
        main_class = classes[0] if classes else None

        # 检测格式
        fmt = self._detect_format(elem)

        result = {
            "html": str(elem),
            "class": main_class,
            "text": elem.get_text(strip=True),
            "format": fmt,
            "table": None
        }

        # 解析表格
        if fmt in ("infobox_table", "table", "mcui"):
            result["table"] = self._parse_table(elem, fmt)

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

    def _parse_table(self, elem, fmt: str) -> list[list[str]]:
        """
        解析HTML表格

        Args:
            elem: BeautifulSoup元素
            fmt: 格式类型

        Returns:
            表格数据，每行是字符串列表
        """
        rows = []

        if fmt == "infobox_table":
            # Infobox 表格：每行包含 label 和 field
            for row in elem.find_all(class_='infobox-row'):
                label = row.find(class_='infobox-row-label')
                field = row.find(class_='infobox-row-field')
                label_text = label.get_text(strip=True) if label else ''
                field_text = field.get_text(strip=True) if field else ''
                rows.append([label_text, field_text])
        elif fmt == "mcui":
            # mcui 格式（合成台/熔炉/织布机/锻造台）
            elem_classes = elem.get('class') or []
            if 'mcui' in elem_classes:
                # elem 本身就是 mcui
                text = self._parse_mcui(elem)
                rows.append([text])
            else:
                # elem 是容器，内部有 mcui
                for mcui in elem.find_all(class_='mcui'):
                    text = self._parse_mcui(mcui)
                    rows.append([text])
        else:
            # 一般表格：解析HTML table
            # elem可能是 table 或包含 table 的容器
            table = elem if elem.name == 'table' else elem.find('table')
            if table:
                for tr in table.find_all('tr'):
                    cells = []
                    for cell in tr.find_all(['th', 'td']):
                        mcui = cell.find(class_='mcui')
                        if mcui:
                            text = self._parse_mcui(mcui)
                        else:
                            text = cell.get_text(separator=' ', strip=True)
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
        mcui_classes = mcui.get('class') or []
        is_furnace = any('Furnace' in c for c in mcui_classes)
        is_smithing = any('Smithing' in c for c in mcui_classes)

        # 收集所有输入槽位
        inputs = []

        if is_smithing:
            # Smithing: 多个 invslot 直接挂在 mcui 下，没有 mcui-input 包装
            slots = self._collect_smithing_inputs(mcui)
            if slots:
                inputs.append(' + '.join(slots))
        else:
            # 合成/熔炉/Loom
            mcui_input = mcui.find(class_='mcui-input')
            if mcui_input:
                if is_furnace:
                    inputs.append(self._parse_furnace_input(mcui_input))
                elif mcui_input.find(class_='mcui-row'):
                    inputs.append(self._parse_grid_input(mcui_input))
                else:
                    inputs.append(self._parse_single_input(mcui_input))

            # mcui-inputPattern (Loom 特殊命名)
            mcui_input_pattern = mcui.find(class_='mcui-inputPattern')
            if mcui_input_pattern:
                pat = self._parse_single_input(mcui_input_pattern)
                if pat:
                    inputs.append(pat)

        inputs = [i for i in inputs if i]
        if inputs:
            parts.append(' '.join(inputs))

        # 输出：smithing 的输出 invslot 也在 mcui 直接子级
        if is_smithing:
            output_text = self._collect_smithing_output(mcui)
            if output_text:
                parts.append(f'-> {output_text}')
        else:
            mcui_output = mcui.find(class_='mcui-output')
            if mcui_output:
                output = self._parse_output(mcui_output)
                if output:
                    parts.append(f'-> {output}')

        return ' '.join(parts) if parts else '?'

    def _parse_single_input(self, container) -> str:
        """解析单个输入槽位"""
        items = container.find_all(class_='invslot-item')
        if not items:
            return ''
        return '/'.join(self._format_item(i) for i in items)

    def _collect_smithing_inputs(self, mcui) -> list[str]:
        """Smithing 模板：invslot 在 template-Smithing_Table-slots 下"""
        slots_container = mcui.find(class_='template-Smithing_Table-slots')
        if not slots_container:
            return []
        result = []
        for child in slots_container.children:
            if not hasattr(child, 'get') or not child.get('class'):
                continue
            cls = child.get('class') or []
            if 'searchaux' in cls:
                continue
            if 'invslot' in cls:
                # 跳过输出槽（通过 style="margin-left: 72px" 区分）
                style = child.get('style', '')
                if 'margin-left' in style:
                    continue
                item = child.find(class_='invslot-item')
                if item:
                    result.append(self._format_item(item))
        return result

    def _collect_smithing_output(self, mcui) -> str:
        """Smithing 模板的输出：通过 style="margin-left: 72px" 标识"""
        slots_container = mcui.find(class_='template-Smithing_Table-slots')
        if not slots_container:
            return ''
        for child in slots_container.children:
            if not hasattr(child, 'get') or not child.get('class'):
                continue
            cls = child.get('class') or []
            if 'invslot' in cls:
                style = child.get('style', '')
                if 'margin-left' in style:
                    item = child.find(class_='invslot-item')
                    if item:
                        title = self.formatter.clean(item.get('title', '?'))
                        return title
        return ''

    def _parse_grid_input(self, mcui_input) -> str:
        """
        3x3 网格输入：每行独立，用 | 分隔单元格，/ 分隔行
        [[|]] searchaux 标记代表空位置
        """
        rows_text = []
        for row in mcui_input.find_all(class_='mcui-row'):
            cells = []
            for child in row.children:
                if not hasattr(child, 'get'):
                    continue
                cls = child.get('class') or []
                if not cls:
                    continue
                if 'searchaux' in cls:
                    # 隐藏 [[|]] 标记：代表空位置
                    cells.append('_')
                elif 'invslot' in cls:
                    items = child.find_all(class_='invslot-item')
                    if items:
                        cell_text = '/'.join(self._format_item(i) for i in items)
                        cells.append(cell_text)
                    else:
                        cells.append('_')
            rows_text.append('|'.join(cells))
        return '[' + ' / '.join(rows_text) + ']'

    def _parse_furnace_input(self, mcui_input) -> str:
        """熔炉输入：物品 + 燃料"""
        parts = []
        for child in mcui_input.children:
            if not hasattr(child, 'get'):
                continue
            cls = child.get('class') or []
            if not cls:
                continue
            if 'searchaux' in cls:
                continue  # 跳过 [[|]] 隐藏标记
            elif 'mcui-fuel' in cls:
                parts.append('+ 任意燃料')
            elif 'invslot' in cls:
                items = child.find_all(class_='invslot-item')
                if items:
                    titles = '/'.join(self._format_item(i) for i in items)
                    parts.append(titles)
        return ' '.join(parts)

    def _format_item(self, item) -> str:
        """格式化单个物品（含数量）"""
        title = self.formatter.clean(item.get('title', '?'))
        # 查找所在 invslot 的 stacksize
        parent = item.find_parent(class_='invslot')
        if parent:
            ss = parent.find(class_='invslot-stacksize')
            if ss:
                count = ss.get_text(strip=True)
                return f'{title}x{count}'
        return title

    def _parse_output(self, mcui_output) -> str:
        """输出物品"""
        for child in mcui_output.children:
            if not (hasattr(child, 'get') and child.get('class')):
                continue
            cls = child.get('class') or []
            if 'searchaux' in cls:
                continue
            elif 'invslot' in cls:
                item = child.find(class_='invslot-item')
                if item:
                    title = self.formatter.clean(item.get('title', '?'))
                    ss = child.find(class_='invslot-stacksize')
                    count = f'x{ss.get_text()}' if ss else ''
                    return f'{title}{count}'
        return ''
