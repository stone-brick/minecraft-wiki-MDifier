"""
模板展开器

通过 MediaWiki API 展开模板，获取渲染后的HTML
"""

from collections.abc import Callable

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from mdifier.exceptions import BucketAPIError, InvalidInputError
from mdifier.formatters import MinecraftColorFormatter
from mdifier.wiki import LANG_CONFIG, USER_AGENT

# 格式检测器：(elem) -> 格式字符串 | None
# 注册表形式，按优先级顺序匹配；首个返回非 None 的获胜
FormatDetector = Callable[[object], str | None]
FORMAT_DETECTORS: list[FormatDetector] = [
    # 1. zh wiki infobox 表格
    lambda e: "infobox_table" if e.find(class_="infobox-row") else None,
    # 2. mcui（elem 本身有 mcui class，或内部有 mcui 元素）
    #    优先于一般表格检测，确保含 mcui 单元格的 wikitable 走 mcui 分支
    lambda e: "mcui" if ("mcui" in (e.get("class") or []) or e.find(class_="mcui")) else None,
    # 3. 一般表格（elem 是 table 且内部无 mcui）
    lambda e: "table" if e.name == "table" and not e.find(class_="mcui") else None,
]

# Bucket API 模板注册表：模板名（小写）→ Bucket 查询配置
# 仅 en wiki 支持 action=bucket
# header/columns 为 None 时从第一条返回数据动态生成
# where 格式：[("bucket_field", "param_name")]
#   param_name: "item"=物品名参数, "1"=位置参数, "_page_title"=页面标题
# 注意：ID table / Biome ID table 不走 bucket API（action=parse 就有数据）
BUCKET_TEMPLATES: dict[str, dict] = {
    "trade uses": {
        "bucket_fn": "trade",
        "where": [("wanted_item", "item")],
        "header": ["Villager", "Level", "Villager wants", "Player receives", "JE", "BE"],
        "columns": [
            "profession",
            "level",
            "wanted_item",
            "given_item",
            "java_probability",
            "bedrock_probability",
        ],
    },
    "trade sources": {
        "bucket_fn": "trade",
        "where": [("wanted_item", "item")],
        "header": ["Villager", "Level", "Villager wants", "Player receives", "JE", "BE"],
        "columns": [
            "profession",
            "level",
            "wanted_item",
            "given_item",
            "java_probability",
            "bedrock_probability",
        ],
    },
    "crafting usage": {
        "bucket_fn": "crafting_recipe",
        "where": [("ingredient", "item")],
        "header": None,
        "columns": None,
    },
    "mob spawn table": {
        "bucket_fn": "spawn_table",
        "where": [("mob", "item")],
        "header": None,
        "columns": None,
    },
}


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

    def expand(self, template_call: str, page_title: str | None = None) -> dict:
        """
        展开模板调用

        Args:
            template_call: 模板调用字符串，如 "{{Hatnote|text}}"
            page_title: 页面标题（用于 bucket 查询的默认值）

        Returns:
            dict: {
                "html": 渲染后的HTML,
                "class": HTML元素的class,
                "text": 提取的文本内容,
                "format": 格式类型 ("text", "infobox_table", "table"),
                "table": 表格数据（如果有的话）
            }
        """
        # 解析模板名和参数
        template_name, params = self._parse_template_call(template_call)

        # 尝试 Bucket API（仅支持 bucket 的 wiki 且命中注册表）
        if self._needs_bucket_api(template_name):
            # 获取英文名用于 bucket 查询（zh/ja wiki 需要翻译页面名）
            english_title = (
                self._get_english_title(page_title) if self.lang in ("zh", "ja") else page_title
            )
            bucket_query = self._build_bucket_query(
                template_name, params, page_title, english_title
            )
            if bucket_query:
                try:
                    return self._expand_via_bucket(bucket_query, template_name)
                except BucketAPIError:
                    pass  # 降级到 action=parse

        # 降级到 action=parse
        return self._expand_via_parse(template_call)

    def _parse_template_call(self, template_call: str) -> tuple[str, dict[str, str]]:
        """
        从模板调用字符串解析模板名和参数

        Args:
            template_call: 如 "{{Hatnote|text}}" 或 "{{Trade uses|Iron Ingot}}"

        Returns:
            (模板名, 参数字典)
        """
        # 去掉 {{ 和 }}
        inner = template_call.strip().lstrip("{").rstrip("}").rstrip("{").rstrip("}")
        parts = inner.split("|")
        name = parts[0].strip()
        # 移除命名空间前缀
        if ":" in name:
            name = name.split(":", 1)[1]

        params = {}
        for i, part in enumerate(parts[1:], start=1):
            part = part.strip()
            if "=" in part:
                key, value = part.split("=", 1)
                params[key.strip()] = value.strip()
            else:
                params[str(i)] = part

        return name, params

    def _needs_bucket_api(self, template_name: str) -> bool:
        """判断模板是否需要走 bucket API"""
        return template_name.lower() in BUCKET_TEMPLATES

    def _build_bucket_query(
        self,
        template_name: str,
        params: dict[str, str],
        page_title: str | None = None,
        english_title: str | None = None,
    ) -> str | None:
        """
        从模板参数构建 bucket 查询语句

        Args:
            template_name: 模板名（如 "Trade uses"）
            params: 模板参数
            page_title: 页面标题（作为默认值）
            english_title: 英文标题（用于 zh/ja wiki bucket 查询）

        Returns:
            bucket 查询语句，或 None（缺少必需参数时）
        """
        info = BUCKET_TEMPLATES.get(template_name.lower())
        if not info:
            return None

        # 优先使用英文标题（zh/ja wiki 通过 langlinks 获取）
        fallback = english_title or page_title
        # where 配置格式：[("field", "param_name")]
        # param_name 可以是 "item", "1", "nameid" 等
        # 特殊值 "_page_title" 表示使用 page_title
        for _, param_name in info["where"]:
            if param_name == "_page_title":
                item = page_title
            else:
                item = params.get(param_name) or params.get("1") or fallback
            if item:
                break

        if not item:
            return None

        where_clauses = []
        for field, _ in info["where"]:
            where_clauses.append(f'"{field}", "{item}"')
        where_str = ",".join(where_clauses)
        # Lua where 语法：{{field, value}} 表示数组的数组
        # f-string 中 { 需要转义为 {{，所以 {{ { }} }} 写作 {{{{ { }} }}}
        return f'bucket("{info["bucket_fn"]}").select("json").where({{{{{where_str}}}}}).run()'

    def _expand_via_bucket(self, query: str, template_name: str) -> dict:
        """
        调用 bucket API 并转换结果

        Args:
            query: bucket 查询语句
            template_name: 模板名（用于获取字段映射）

        Returns:
            标准展开结果 dict
        """
        params = {
            "action": "bucket",
            "query": query,
            "format": "json",
        }
        resp = self.session.get(self.api_url, params=params)
        data = resp.json()

        bucket_data = data.get("bucket", [])
        table = self._convert_bucket_json_to_table(bucket_data, template_name)

        return {
            "html": "",
            "class": template_name.lower().replace(" ", "_"),
            "text": "",
            "format": "table",
            "table": table,
            "template_name": template_name,
        }

    def _convert_bucket_json_to_table(
        self, bucket_data: list[dict], template_name: str
    ) -> list[list[str]]:
        """
        将 bucket API 返回的嵌套 JSON 转换为 table 格式

        Args:
            bucket_data: API 返回的 [{"json": "{...}"}, ...]
            template_name: 模板名（用于获取字段映射）

        Returns:
            table 二维数组（含表头行）
        """
        import json

        info = BUCKET_TEMPLATES.get(template_name.lower(), {})
        columns = info.get("columns")
        header = info.get("header")

        # 如果 columns/header 为 None，从第一条数据动态生成
        if columns is None or header is None:
            first_data = None
            for entry in bucket_data:
                try:
                    first_data = json.loads(entry.get("json", "{}"))
                    break
                except json.JSONDecodeError:
                    continue

            if first_data:
                if columns is None:
                    # 使用第一层 keys 作为 columns
                    columns = list(first_data.keys())
                if header is None:
                    # 将 keys 转换为友好表头：profession → Profession
                    header = [self._format_header_key(k) for k in columns]
            else:
                columns = []
                header = []

        rows = []
        # 添加表头行
        if header:
            rows.append(header)

        for entry in bucket_data:
            json_str = entry.get("json", "{}")
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                continue

            row = []
            for col in columns:
                if col == "wanted_item":
                    quant = data.get("wanted_quant", "1")
                    item = self._translate_field(data, "wanted_item")
                    if quant and quant != "1":
                        row.append(f"{quant}× {item}")
                    else:
                        row.append(item)
                elif col == "given_item":
                    quant = data.get("given_quant", "1")
                    item = self._translate_field(data, "given_item")
                    if quant and quant != "1":
                        row.append(f"{quant}× {item}")
                    else:
                        row.append(item)
                else:
                    val = (
                        self._translate_field(data, col) if self.lang == "zh" else data.get(col, "")
                    )
                    row.append(val if val else "")

            if any(row):
                rows.append(row)

        return rows

    def _format_header_key(self, key: str) -> str:
        """将字段名转换为友好的表头：profession → Profession"""
        # 简单首字母大写转换，下划线/驼峰拆词
        result = key.replace("_", " ").replace("-", " ")
        return result.title()

    def _translate_field(self, data: dict, key: str) -> str:
        """
        翻译字段，优先使用 i18n 版本（zh wiki）

        Args:
            data: bucket JSON 数据
            key: 字段名（如 "profession", "level"）

        Returns:
            翻译后的值
        """
        # i18n key 格式：profession_i18n, level_i18n
        i18n_key = f"{key}_i18n"
        if i18n_key in data and data[i18n_key]:
            return data[i18n_key]
        return data.get(key, "")

    def _get_english_title(self, title: str | None) -> str | None:
        """
        通过 langlinks API 获取页面的英文名（用于 zh/ja wiki bucket 查询）

        Args:
            title: 页面标题

        Returns:
            英文标题，或 None（如果获取失败）
        """
        if not title:
            return None

        params = {
            "action": "query",
            "titles": title,
            "prop": "langlinks",
            "lllang": "en",
            "format": "json",
        }
        try:
            resp = self.session.get(self.api_url, params=params)
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

    def _expand_via_parse(self, template_call: str) -> dict:
        """
        通过 action=parse API 展开模板

        Args:
            template_call: 模板调用字符串

        Returns:
            标准展开结果 dict
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

        # 提取 history-json pre 数据（en wiki 元数据块）
        infobox_json = None
        for pre in soup.find_all("pre", class_=lambda c: c and "history-json" in c):
            try:
                import json

                infobox_json = json.loads(pre.get_text(strip=True))
            except Exception:
                pass

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

        # 检测格式（infobox_json 已提取，pre 尚未移除）
        fmt = self._detect_format(elem, infobox_json)

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

        # infobox_table 已提取 history-json 数据，移除 pre 避免 markdownify 生成代码块
        if fmt == "infobox_table":
            for pre in soup.find_all("pre", class_=lambda c: c and "history-json" in c):
                pre.decompose()

        return result

    def _detect_format(self, elem, infobox_json: dict | None = None) -> str:
        """
        检测HTML格式类型

        Args:
            elem: BeautifulSoup元素
            infobox_json: history-json 数据（如果存在）

        Returns:
            格式类型: "text", "infobox_table", "table", "mcui"
        """
        # 第 0 条：同时有 infobox-rows table 和 history-json pre → history-json 模式
        if infobox_json is not None and elem.find(class_="infobox-rows"):
            return "infobox_table"
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
