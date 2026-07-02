<div align="center">

# ⚡ Minecraft Wiki MDifier

专为 AI 工具打造：将 Minecraft Wiki 完美转换为纯净、结构化的 Markdown 格式。

[![PyPI version](https://img.shields.io/pypi/v/minecraft-wiki-mdifier.svg)](https://pypi.org/project/minecraft-wiki-mdifier/)

**[English](./README-en.md)** · **[日本語](./README-ja.md)**

</div>

## 起源

用了 AI 助手之后就再也回不去了——我不想再纯手搓数据包。
但获取 Minecraft Wiki 内容时，纯 HTML 夹杂样式碎片，纯 wikitext 通用解析器又处理不了。

于是自己写了一个。GitHub 上搜了一圈没有找到现成的，后来发现了 @L3-N0X 的 Minecraft-Wiki-MCP 需要更好的解析支持（现在已重构），我意识到大家可能需要这个工具。

## 问题与解决

在处理 Minecraft Wiki 时会遇到以下难题：

1. **模板展开慢** — Wiki 页面中的模板引用需要逐个展开，逐一请求耗时巨大。
2. **清理不全** — 渲染后的 HTML 包含大量无用的 class、style、data 属性和冗余标签。
3. **Wikitext 语法混乱** — Bold/Italic 标签嵌套、`{{end-bold}}` 等 MediaWiki 特有语法，通用解析器容易误判。
4. **HTML 占用上下文且干扰语义** — 纯 HTML 包含大量无关标签，浪费 token 且影响 LLM 理解。
5. **模板信息省略** — Wikitext 中的模板只是占位符，AI 无法得到结构化数据。

### 解决方案

- **并发 + 缓存**：解决模板展开慢的问题
- **统一 `action=parse`**：所有模板统一走 API 展开，无需 Lua Bucket 数据库
- **Pandoc 预处理**：`pypandoc` 将 wikitext 转为 Markdown，无法处理的模板保留为 `{=mediawiki}` 块再单独展开
- **HTML 清理**：BeautifulSoup + markdownify 清理冗余属性
- **模板标记 `:::name`**：解决模板信息省略的问题

**性能对比**（转换 工作台、苦力怕、苹果、铁锭、Minecraft）：

| 方案        | 耗时   | 加速比      |
| --------- | ------ | --------- |
| 有缓存（冷）    | 78.87s | 1.0x      |
| 有缓存（热）    | 2.48s  | **31.8x** |

## 安装

**需要 Python >= 3.11**

```bash
# 从 PyPI 安装（推荐）
pip install minecraft-wiki-mdifier

# 本地开发模式
pip install -e .
```

安装后验证：

```bash
mdifier --version
# 找不到命令？用 python -m minecraft_wiki_mdifier.cli --version
```

## 快速入门

```bash
# 转换单页（中文 wiki 默认）
mdifier convert "铁锭"

# 保存到文件
mdifier convert "铁锭" -o iron.md

# 英文 wiki
mdifier convert "Iron Ingot" --lang en -o iron.md

# 从 URL 自动识别语言
mdifier convert "https://zh.minecraft.wiki/铁锭"
mdifier convert "https://minecraft.wiki/wiki/Iron_Ingot"

# 搜索页面
mdifier search "钻石"
mdifier search "diamond" --lang en

# 批量转换
mdifier batch -t 钻石 -t 铁锭 -o ./out
mdifier batch -i pages.txt -o ./out --workers 8
mdifier batch -t Diamond --lang en --no-markers  # 禁用模板标记

# 缓存管理
mdifier cache info
mdifier cache clear -y   # 清空缓存
mdifier cache prune       # 清理过期条目
```

## 应用场景

**MCP / Skills / Agent 构建**
为 AI 助手提供 Minecraft Wiki 数据源，构建可以回答游戏问题的 Agent。

```python
from minecraft_wiki_mdifier import convert_many

pages = ["钻石", "铁锭", "金锭", "绿宝石", "青金石"]
result = convert_many(pages)
# 输出干净 Markdown，可直接用于上下文注入
```

**RAG 知识库**
将 Wiki 内容向量化，构建本地知识库：

```python
result = convert_detailed("Iron Ingot")
print(result.markdown)  # 干净文本，可直接用于分块和向量化
```

**MOD 开发数据查询**
获取村民交易、怪物掉落等结构化数据：

```python
from minecraft_wiki_mdifier import convert_detailed

result = convert_detailed("Armorer")
print(result.templates["trade"])  # 渲染后的交易表格 Markdown
```

## CLI 参考

### convert

```bash
mdifier convert "TITLE_OR_URL" [-o OUTPUT] [--lang {zh|en|ja}] [--detail]
```

| 选项             | 说明                                           |
| -------------- | -------------------------------------------- |
| `-o, --output` | 输出文件路径                                       |
| `-l, --lang`   | 语言（默认 zh）                                    |
| `--detail`     | 输出完整 JSON（含 title、markdown、source、templates） |

### search

```bash
mdifier search "QUERY" [-l {zh|en|ja}] [-n NUM]
```

| 选项           | 说明           |
| ------------ | ------------ |
| `-l, --lang` | 语言（默认 zh）    |
| `-n NUM`     | 返回结果数（默认 10） |

### batch

```bash
mdifier batch [-t TITLE] [-i FILE] [--from-search QUERY] [-o DIR] [--workers N] [--no-progress] [--marker-format FORMAT]
```

| 选项                 | 说明                                         |
| ------------------ | ------------------------------------------ |
| `-t, --title`      | 页面标题（可多次使用）                                |
| `-i, --input-file` | 标题列表文件（每行一个，`#` 开头为注释）                     |
| `--from-search`    | 通过搜索获取标题                                   |
| `--search-limit`   | `--from-search` 时返回的最大结果数                  |
| `-o, --output-dir` | 输出目录；为 None 则打印到 stdout                    |
| `--workers`        | 跨页并发抓取数（默认 4）                              |
| `--no-progress`    | 禁用进度条                                      |
| `--marker-format`  | 自定义模板标记，格式 `open/close`（`{name}` 为模板类名占位符） |
| `--no-markers`     | 禁用模板起讫标记（`:::name`）                        |

### cache

```bash
mdifier cache info|clear|prune
```

- `info` — 显示统计（路径、大小、条目数、过期数、时间戳）
- `clear` — 清空整个缓存（加 `-y` 跳过确认）
- `prune` — 仅清理已过期条目

## Python API

```python
from minecraft_wiki_mdifier import convert, convert_detailed, convert_many, search

# 简单转换
md = convert("铁锭")

# 详细模式
result = convert_detailed("铁锭")
print(result.title)      # 页面标题
print(result.source)     # "api" 或 "html"
print(result.templates)  # 模板数据 dict

# 批量转换
result = convert_many(["钻石", "铁锭", "附魔台"], max_workers=4)
for r in result.results:
    print(f"=== {r.title} ===")
if result.failed:
    print(f"失败: {result.failed}")
if result.unresolved:
    print(f"未展开模板: {result.unresolved}")

# 搜索
results = search("diamond", lang="en")
for r in results[:5]:
    print(f"{r['title']}: {r['description']}")
```

### URL 自动识别

| 输入                                       | 识别语言                |
| ---------------------------------------- | ------------------- |
| `https://zh.minecraft.wiki/wiki/铁锭`      | zh                  |
| `https://minecraft.wiki/wiki/Iron_Ingot` | en                  |
| `https://ja.minecraft.wiki/wiki/鉄`       | ja                  |
| 纯标题                                      | 使用 `lang` 参数（默认 zh） |

### 跨语言批量

```python
items = [
    "钻石",                                      # zh
    "https://minecraft.wiki/wiki/Diamond",      # en（URL 识别）
    "Iron Ingot",                                # 使用默认 lang
]
result = convert_many(items, lang="zh")
```

## 高级用法

### 模板标记自定义

```python
from minecraft_wiki_mdifier.converter import MarkdownConverter

c = MarkdownConverter()
c.template_marker_open = '<details><summary>{name}</summary>'
c.template_marker_close = '</details>'
```

CLI 端用 `--marker-format`：

```bash
mdifier batch -t 钻石 --marker-format '<details><summary>{name}</summary></details>/</details>'
# 格式为 open/close，即 <开启标签>/<闭合标签>
```

### 批量取消

```python
import threading
from minecraft_wiki_mdifier.converter import MarkdownConverter

c = MarkdownConverter(lang='zh')
threading.Timer(0.5, c.cancel).start()  # 0.5 秒后取消

convert_many(['钻石', '铁锭', '附魔台'],
             converter_factory=lambda l, cache: c)

print(c.is_cancelled())       # True
print(c.unresolved_templates) # frozenset({'HistoryTable', ...})
```

### 跨调用共享缓存

```python
shared = {}
convert("钻石", template_cache=shared)   # 24 条模板展开
convert("铁锭", template_cache=shared)   # 增量 17 条，24 条共享
```

注意：`template_cache` 参数是进程内共享，不写盘；磁盘缓存（`~/.cache/mdifier/`）跨进程共享。

### 颜色代码

```python
from minecraft_wiki_mdifier.formatters import MinecraftColorFormatter

f = MinecraftColorFormatter()
f.clean("&e黄色&r重置")  # '[yellow]黄色[reset]重置'
```

## 模板处理

模板被包裹在 `:::{name}` 标记中，内容按格式分发渲染：

| 模板                     | 输出                                    |
| ---------------------- | ------------------------------------- |
| `Infobox`（物品信息框）       | 两列 Markdown 表格                        |
| `Crafting`（合成表）        | 三列：材料 / 配方 / 描述                       |
| `DropTable`（掉落表）      | Markdown 表格 + 掉落注释脚注（`[^A]` 等）       |
| `mcui`（合成台/熔炉/织布机/锻造台） | 3x3 网格文本 + 物品描述                       |
| `Hatnote`、`Quote`      | markdownify 转为 Markdown               |
| 其他未识别模板                | 通用 markdownify 转换                     |
| 展开失败                   | 回退文本 `[模板名: k=v]`，标记为 `class="error"` |

所有模板统一通过 `action=parse` API 展开，缓存命中时无需网络请求。

## 缓存机制

- **位置**：`~/.cache/mdifier/templates.json`
- **TTL**：7 天
- **共享**：跨进程、跨运行
- **加速**：首次 ~6s，二次 ~1s（约 **5.4x**）

Python API：

```python
from minecraft_wiki_mdifier.cache import cache_info, clear_cache

info = cache_info()
if info["size_mb"] > 100:
    clear_cache()
```

## 错误处理

### Python 异常

```python
from minecraft_wiki_mdifier import convert, InvalidInputError

try:
    md = convert("nonexistent_xyz_123")
except InvalidInputError as e:  # 继承自 ValueError
    print(f"失败: {e}")
```

**异常层级**：

```
MdifierError
├── InvalidInputError (ValueError)
├── FetchError (requests.RequestException)
│   ├── NetworkError
│   ├── WikiAPIError
│   └── PageNotFoundError
└── CacheError (OSError)
```

### CLI 退出码

| 退出码 | 名称            | 含义                |
| --- | ------------- | ----------------- |
| 0   | 成功            | 全部 OK             |
| 64  | `EX_USAGE`    | 命令行参数错            |
| 65  | `EX_DATAERR`  | 数据错（页面不存在、批量部分失败） |
| 70  | `EX_SOFTWARE` | 内部软件错             |
| 74  | `EX_IOERR`    | 本地 I/O 错          |
| 75  | `EX_TEMPFAIL` | 网络临时失败            |
| 77  | `EX_NOPERM`   | 权限错               |
| 78  | `EXIT_CONFIG` | 配置错              |

## 多语言支持

内置 `zh`（zh.minecraft.wiki）、`en`（minecraft.wiki）和 `ja`（ja.minecraft.wiki）。

## 项目结构

```
src/minecraft_wiki_mdifier/
├── __init__.py           # 导出公共 API
├── lib.py                # convert / convert_many / search
├── cli.py                # CLI 入口（click）
├── wiki.py               # MediaWiki API 获取 + HTML 降级
├── pandoc_trimmer.py     # 核心转换：Pandoc 预处理 + 模板渲染
├── template_expander.py  # 模板展开（action=parse 降级链）
├── formatters.py         # Minecraft 颜色代码格式化
├── converter.py          # Markdown 生成
├── cache.py              # 模板缓存持久化
├── exceptions.py         # 异常层级
├── _session.py           # HTTP Session 工厂
└── _validators.py        # 语言验证器
```

**数据流**：

```
Wikitext
    │
    ▼
pypandoc(commonmark_x+raw_attribute)
    │
    ▼
遍历输出，识别 {=mediawiki} 块和内联模板
    │
    ▼
TemplateExpander.expand() — 统一 action=parse
    │
    ▼
pandoc_trimmer 渲染器分发 — 专用渲染器 > 通用 markdownify
    │
    ▼
Markdown
```

> **注意**：`parser.py` 在当前架构下未使用，是遗留代码。

## 参与贡献

欢迎任何形式的贡献：

- 🐛 发现 Bug？请 [提交 Issue](https://github.com/stone-brick/minecraft-wiki-MDifier/issues)
- 💡 有好想法？欢迎 [讨论](https://github.com/stone-brick/minecraft-wiki-MDifier/discussions)
- 📖 或许你有更好的实现？直接发 PR 吧

### 开发环境

```bash
git clone https://github.com/stone-brick/minecraft-wiki-MDifier
cd minecraft-wiki-MDifier
pip install -e ".[dev]"
pytest
```

## License

MIT
