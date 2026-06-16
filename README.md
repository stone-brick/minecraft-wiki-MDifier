<div align="center">

# ⚡ Minecraft Wiki MDifier

将 Minecraft Wiki 页面转换为 AI 助手易读的 Markdown 格式

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)

**[English](./README-en.md)** · **[日本語](./README-ja.md)**

</div>

## 安装

**需要 Python >= 3.11**，依赖：`requests`, `beautifulsoup4`, `click`, `markdownify`。

```bash
# 从 PyPI 安装（推荐）
pip install minecraft-wiki-mdifier

# 本地开发模式（可编辑）
pip install -e .
```

### PATH 设置

`mdifier` 命令装在 Python 的 Scripts 目录。如果终端找不到命令：

**Windows (Git Bash / PowerShell)**：
```bash
# 找到 Scripts 路径（一般输出形如 C:\Program Files\Python\Python313\Scripts）
python -c "import sysconfig; print(sysconfig.get_paths()['scripts'])"
# 临时加 PATH（替换上面输出的实际路径，Git Bash 用正斜杠）
export PATH="$PATH:/d/Program\ Files/Python/Python313/Scripts"
# 永久加：把上述加到 ~/.bashrc
```

**macOS / Linux**：
```bash
# 通常 pip install 会自动装到 ~/.local/bin
export PATH="$PATH:$HOME/.local/bin"
# 或：python -m minecraft_wiki_mdifier.cli（跨平台等价）
```

验证：
```bash
mdifier --version
# 如不行：python -m minecraft_wiki_mdifier.cli --version
```

### 路径最佳实践（AI 助手必看）

`-o` 和 `-i` 参数的路径处理**因 shell 而异**。为避免混乱，**推荐使用相对路径**：

| 路径形式 | PowerShell | Git Bash | 推荐度 |
|----------|------------|----------|--------|
| `output/x.md`（相对） | cwd | cwd | 🥇 跨 shell 一致 |
| `D:/tests/x.md`（Windows 绝对） | D:\tests\x.md | D:\tests\x.md | 🥈 两 shell 都认 |
| `/tests/x.md`（Unix 绝对） | **D:\tests\x.md**（字面）| D:\Program Files\Git\tests（MSYS 翻译） | ❌ 行为不一致 |

**为什么 PowerShell 把 `/tests/x.md` 写到 D:\tests\？** PowerShell 不会做 MSYS 翻译，按字面理解路径，相当于 `D:\tests\x.md`（D: 是当前盘符）。

**为什么 Git Bash 把 `/tests/x.md` 翻译到 D:\Program Files\Git\tests\？** Git Bash 启动时把 `/` 映射到 Git 安装目录（MSYS 机制），这跟系统根目录不是一回事。

**推荐写法（AI 助手）**：
```bash
# 用相对路径（自动基于当前工作目录）
cd ~/wiki && mdifier convert "铁锭" -o output/iron.md

# 批量时先建子目录
mkdir -p output && mdifier batch -t 钻石 -t 铁锭 -o output/
```

保存路径**会显示为绝对路径**（避免你猜测它在哪）。

### CLI 退出码（BSD sysexits）

| 退出码 | 名称 | 含义 |
|--------|------|------|
| 0 | 成功 | 全部 OK |
| 64 (`EX_USAGE`) | 命令行参数错 | lang、--marker-format 格式 |
| 65 (`EX_DATAERR`) | 数据错 | 页面不存在、批量部分失败 |
| 70 (`EX_SOFTWARE`) | 内部软件错 | 未预期异常 |
| 74 (`EX_IOERR`) | 本地 I/O 错 | 写入文件失败、目录创建失败 |
| 75 (`EX_TEMPFAIL`) | 网络临时失败 | Wiki API 连不上（可重试）|
| 77 (`EX_NOPERM`) | 权限错 | 无写权限 |

错误消息用 `click.secho(..., fg='red')` 染色（管道/非 tty 自动失效）。

## 使用方式

### CLI

```bash
# 转换页面（中文 wiki 默认）
mdifier convert "铁锭"

# 英文 wiki
mdifier convert "Iron Ingot" --lang en -o iron.md

# 输出到文件
mdifier convert "铁锭" -o iron_ingot.md

# 完整 JSON 输出（含 templates）
mdifier convert "铁锭" --detail

# 使用 URL（自动识别语言）
mdifier convert "https://zh.minecraft.wiki/铁锭"
mdifier convert "https://minecraft.wiki/wiki/Iron_Ingot"

# 搜索页面
mdifier search "钻石"
mdifier search "diamond" --lang en
mdifier search "钻石" -n 20  # 返回结果数（默认 10）

# 批量转换：多个标题 → 独立 .md 文件
mdifier batch -t 钻石 -t 铁锭 -t 附魔台 -o ./out
mdifier batch -t Iron_Ingot -t Diamond --lang en -o ./en_out

# 批量转换：从文件读取标题列表（每行一个，# 开头为注释，空行跳过）
mdifier batch -i pages.txt -o ./out --workers 8

# 批量转换：从搜索结果中取前 N 个（--search-limit 默认 20）
mdifier batch --from-search "红石" --search-limit 30 -o ./out

# 批量：禁用进度条
mdifier batch -i pages.txt -o ./out --no-progress

# 缓存管理
mdifier cache info    # 查看缓存状态
mdifier cache clear   # 强制清空缓存（默认会交互确认；加 -y 跳过）
mdifier cache prune   # 仅清理过期条目（保留未过期）

# 自定义模板标记（喂给不同 LLM prompt 风格）
# 格式：open/close，用单个 / 分隔，{name} 是模板类名占位符
mdifier batch -t 钻石 --marker-format '<details><summary>{name}</summary>/</details>'
mdifier batch -t Iron_Ingot --marker-format '<template:{name} start>/<template:{name} end>'
```

没装 pip 或找不到 `mdifier` 命令时，直接用 `python -m` 运行模块：

```bash
python -m minecraft_wiki_mdifier.cli convert "铁锭"
python -m minecraft_wiki_mdifier.cli search "钻石"
```

### Python 库

```python
from minecraft_wiki_mdifier import convert, convert_detailed, convert_many, search, BatchConvertResult, ConvertResult

# 简单转换（中文默认）
md = convert("铁锭")
print(md)

# 英文 wiki
md_en = convert("Iron Ingot", lang="en")

# 详细模式返回 ConvertResult（带 title、source、templates）
# CLI 可用 --detail 等价：mdifier convert "铁锭" --detail
result: ConvertResult = convert_detailed("铁锭")
print(f"标题: {result.title}")
print(f"来源: {result.source}")  # "api" 或 "html"
print(f"模板: {result.templates}")  # 非空 dict，含所有展开后的模板数据
print(f"Markdown 长度: {len(result.markdown)}")

# 跨调用共享缓存（同一进程内多次 convert 不重复请求模板）
shared_cache = {}
convert("钻石", template_cache=shared_cache)
convert("铁锭", template_cache=shared_cache)  # 共享已展开的模板

# 批量转换
result = convert_many(["钻石", "铁锭", "附魔台"], max_workers=4)
for r in result.results:
    print(f"=== {r.title} ===")
    print(r.markdown)
if result.failed:
    print(f"失败: {result.failed}")
if result.unresolved:
    print(f"未展开模板: {result.unresolved}")

# 跨语言批量：混合 URL + 纯标题，内部按 lang 分组
items = [
    "钻石",                                        # zh
    "https://minecraft.wiki/wiki/Diamond",          # en（URL 识别）
    "Iron Ingot",                                  # 使用 --lang 默认值
    "https://zh.minecraft.wiki/wiki/工作台",         # zh
]
result = convert_many(items, lang="zh")

# 进度回调
def on_progress(done, total, title):
    print(f"[{done}/{total}] {title}")
result = convert_many(["钻石", "铁锭", "附魔台"], on_progress=on_progress)

# 搜索
results = search("diamond", lang="en")
for r in results[:5]:
    print(f"{r['title']}: {r['description']} ({r['url']})")
```

### URL 自动识别

| URL 模式 | 识别为 |
|----------|--------|
| `https://zh.minecraft.wiki/wiki/铁锭` | zh |
| `https://zh.minecraft.wiki/铁锭`（省略 `/wiki/`） | zh |
| `https://minecraft.wiki/wiki/Iron_Ingot` | en |
| `https://en.minecraft.wiki/wiki/Diamond` | en |
| `钻石`（纯标题） | 使用 `--lang` 默认值 |

### 错误处理

```python
# 单页 convert 抛 InvalidInputError（继承自 ValueError）
try:
    md = convert("nonexistent_xyz_123")
except InvalidInputError as e:
    print(f"失败: {e}")  # "无法获取页面: nonexistent_xyz_123"

# 批量 convert_many 不抛，仅聚合到 result.failed
result = convert_many(["钻石", "nonexistent_xyz_123"])
for t, err in result.failed:
    print(f"  失败: {t}: {err}")
# CLI 模式下 result.failed 非空时 exit code = 65 (EX_DATAERR)

# 语言不支持抛 InvalidInputError
try:
    convert("X", lang="xx")
except InvalidInputError as e:
    print(e)  # "Unsupported language: xx. Available: ['zh', 'en']"
```

**自定义异常层级**：

| 异常 | 父类 | 含义 |
|------|------|------|
| `MdifierError` | `Exception` | 基类 |
| `InvalidInputError` | `MdifierError`, `ValueError` | 用户输入错误 |
| `FetchError` | `MdifierError`, `requests.RequestException` | 网络错误基类 |
| `NetworkError` | `FetchError` | 连接失败/超时 |
| `WikiAPIError` | `FetchError` | API 异常结构 |
| `PageNotFoundError` | `FetchError` | 页面不存在 |
| `BucketAPIError` | `MdifierError` | Bucket API 调用失败 |
| `CacheError` | `MdifierError`, `OSError` | 缓存读写失败 |

## 功能特点

- **双模式**：CLI（`mdifier`）+ Python 库
- **多语言支持**：内置 `zh`（zh.minecraft.wiki）、`en`（minecraft.wiki）和 `ja`（ja.minecraft.wiki）
  - 注意：ja wiki 的 Bucket i18n 字段含中文内容，程序默认不翻译，输出英文原文
- **批量转换**：`mdifier batch` 子命令支持 -t / -i / --from-search
- **跨语言批量**：标题列表可混合 zh/en/ja 页面，内部自动按语言分组
- **持久化模板缓存**：相同模板只请求一次，跨运行共享（**5.4x 加速**）
- **缓存管理**：`mdifier cache info/clear/prune` 子命令组
- **自动 PascalCase**：仅对全小写、无空格/连字符的纯字母名生效（如 `for` → `For`、`id table` → `Id Table`）
- **未展开报告**：批量结束时报告缺失的模板名
- **模板标记可配置**：可自定义 `<template:xxx>` 标记格式
- **批量可取消**：`MarkdownConverter.cancel()` 中断大批量任务
- **智能获取**：优先 MediaWiki API，HTML 降级抓取
- **网络重试**：HTTP GET 请求自动重试 3 次（指数退避 0.5s/1s/2s），应对瞬时 5xx/429
- **模板适配**：合成表、物品信息框、战利品表等 30+ 常见模板自动展开
- **mcui 解析**：合成台、熔炉、织布机、锻造台的图片化 UI 转语义化文本
- **颜色代码**：Minecraft `&e` `&r` 等格式代码转为 `[yellow]` `[reset]` 等语义标签
- **并发优化**：模板展开使用线程池，单页 4.6x 加速

## 模板处理

模板被包裹在 `:::{name}` 标记中，内容按格式分类型处理：

| 模板 | 输出 |
|------|------|
| `Infobox`（物品信息框） | 两列 Markdown 表格 |
| `Crafting`（合成表） | 三列：材料 / 配方 / 描述 |
| `LootChest`（战利品表） | 六列：物品 / 来源 / 数量 / 概率等 |
| `mcui`（合成台/熔炉/织布机/锻造台） | 3x3 网格文本 + 物品描述 |
| `Hatnote`、`Quote` | 用 markdownify 转为 Markdown 格式 |
| 其他未识别模板 | 通用 markdownify 转换 |
| 展开失败（API 异常） | 回退文本 `[模板名: k=v]`，标记为 `class="error"` |

**输出示例**：

```markdown
### 合成

:::Crafting
| 材料 | 合成 配方 |
| --- | --- |
| 钻石块 | [_|_|_ / _|_|钻石块|_ / _|_|_] -> 钻石x9 |
:::
```

## 性能与缓存

### 缓存机制

模板展开结果自动持久化到磁盘：

- **位置**：`~/.cache/mdifier/templates.json`（Windows: `C:\Users\<user>\.cache\mdifier\`）
- **大小**：~1 MB / 1000 模板
- **TTL**：7 天（过期自动失效）
- **共享**：跨进程、跨运行、跨项目

### 性能数据

| 场景 | 耗时 |
|------|------|
| 首次运行（建立缓存） | ~6s |
| 二次运行（命中缓存） | ~1s |
| **加速比** | **5.4x** |

### 自定义模板标记

可改为 HTML `details` 等风格。`open` 和 `close` 各自可独立配置：

```python
from minecraft_wiki_mdifier.converter import MarkdownConverter

c = MarkdownConverter()
c.template_marker_open = ":::{name}"
c.template_marker_close = ":::"

# 输出示例：
# :::infobox
# ...内容...
# :::

# 也可以 HTML 风格
c.template_marker_open = "<details><summary>{name}</summary>"
c.template_marker_close = "</details>"
```

CLI 端用 `--marker-format`（格式：`open/close`，用单个 `/` 分隔，`{name}` 是模板类名占位符）：

```bash
mdifier batch -t 钻石 --marker-format '<details><summary>{name}</summary>/</details>'
mdifier batch -i pages.txt --marker-format '<template:{name} start>/<template:{name} end>'
```

### 批量取消（API 用户）

通过 `converter_factory` 参数获得 converter 引用，从其他线程调用 `cancel()`：

```python
import threading
from minecraft_wiki_mdifier import convert_many
from minecraft_wiki_mdifier.converter import MarkdownConverter

c = MarkdownConverter(lang='zh')
threading.Timer(0.5, c.cancel).start()
# 0.5 秒后自动取消批量任务
convert_many(['钻石', '铁锭', '附魔台'],
             converter_factory=lambda l, cache: c)

# 取消后可检查状态和未展开模板
print(c.is_cancelled())          # True
print(c.unresolved_templates)    # frozenset({'HistoryTable', ...})
```

### 批量输出文件命名

批量输出文件（`-o out_dir/`）按以下规则生成文件名：

- 页面标题经 `_slug()` 处理：非法文件名字符（`\ / : * ? " < > |`）→ `_`；空格→`_`；emoji 等高位 Unicode → 移除
- 标题为空时回退为 `untitled`
- 同名冲突：自动加 `-2`、`-3` 后缀，超过 999 次冲突则用 uuid 前 6 位

### 输入文件格式（`-i`）

```
# 注释行（# 开头）
钻石
铁锭
    # 空行自动跳过
Iron Ingot
```

### 跨调用共享缓存（不持久化）

单页 `convert` 也支持传入 `template_cache`，同一进程内多次转换共享模板展开结果：

```python
from minecraft_wiki_mdifier import convert

shared = {}
convert("钻石", template_cache=shared)  # 24 条模板展开
convert("铁锭", template_cache=shared)  # 增量 17 条，24 条共享
```

**与磁盘缓存的区别**：
- `template_cache` 参数：进程内共享，不写盘
- 磁盘缓存（`~/.cache/mdifier/`）：跨进程、跨运行共享
- `convert_many()` 内部使用磁盘缓存；不写单页 `convert` 的中间缓存

### 缓存管理命令对比

| 命令 | 行为 | 适用场景 |
|------|------|----------|
| `mdifier cache info` | 显示统计（只读） | 查看缓存状态 |
| `mdifier cache clear` | 删除整个缓存文件 | wiki 大改，强制重建 |
| `mdifier cache prune` | 保留未过期（< 7 天），仅删除过期 | 日常维护 |

注：`cache clear` 默认会交互确认（除非 `-y`）。

**Python API 等效**：

```python
from minecraft_wiki_mdifier.cache import cache_info, clear_cache, save_cache

# 手动将进程内缓存写入磁盘（convert_many 自动调用）
save_cache(my_cache_dict)

# 等价于 cache clear
clear_cache()
```

### `cache_info()` 返回字段

| 字段 | 类型 | 含义 |
|------|------|------|
| `path` | str | 缓存文件路径 |
| `exists` | bool | 是否存在 |
| `size_bytes` | int | 字节数 |
| `size_mb` | float | MB（保留 2 位小数）|
| `entries` | int | 总条目数 |
| `fresh_entries` | int | 未过期条目数 |
| `expired_entries` | int | 已过期条目数 |
| `oldest_ts` | str | 最早时间戳（ISO 格式）|
| `newest_ts` | str | 最新时间戳（ISO 格式）|

Python 等价：

```python
from minecraft_wiki_mdifier.cache import cache_info, clear_cache

info = cache_info()
if info["exists"] and info["size_mb"] > 100:
    clear_cache()  # 清理
```

## 项目结构

```
src/minecraft_wiki_mdifier/
├── __init__.py           # 导出 convert/convert_detailed/convert_many/search
├── lib.py                # 库模式 API（含 convert_many）
├── cli.py                # CLI 入口（click，含 batch/cache 子命令）
├── wiki.py               # MediaWiki API 获取 + HTML 降级
├── parser.py             # Wikitext 解析器（模板/链接/标题）
├── template_expander.py  # 模板展开：action=bucket 或 action=parse + 格式检测
├── formatters.py         # Minecraft 颜色代码 → 语义化标签
├── converter.py          # Markdown 生成：dict dispatch 渲染
├── cache.py              # 模板展开缓存持久化
├── exceptions.py         # 自定义异常层级（含 BucketAPIError）
├── _session.py           # HTTP Session 工厂（统一重试配置、User-Agent）
└── _validators.py        # 语言验证器（避免循环依赖）
```

### 数据流

1. `WikiFetcher` → MediaWiki API 获取 wikitext
2. `WikiParser` → 解析 AST，提取模板到 `templates` 字典
3. `TemplateExpander` → 对 Lua 数据查询模板（Trade uses 等）优先尝试 `action=bucket`，失败则降级到 `action=parse`
4. `MarkdownConverter` → 按格式分发到对应渲染器，生成最终 Markdown
5. 跨运行：`get_or_load_persistent_cache()` 模块级单例懒加载磁盘缓存；批量结束仅 `save_cache()` 一次

## 开发

### 安装开发依赖

```bash
pip install -e ".[dev]"
pre-commit install
```

### 运行 ruff 检查

```bash
ruff check .
```

或通过 pre-commit 自动触发（提交时自动运行）：

```bash
pre-commit run --all-files
```

### 手动测试

```bash
# 转换单页
mdifier convert "钻石" -o diamond.md

# 多页批量
for page in 钻石 铁锭 附魔台; do
    mdifier convert "$page" -o "${page}.md"
done

# 缓存管理
mdifier cache info
mdifier cache clear -y
```

## 高级选项

### `MarkdownConverter` 构造参数

```python
from minecraft_wiki_mdifier.converter import MarkdownConverter

c = MarkdownConverter(
    lang="zh",                   # 语言：zh / en / ja
    max_workers=10,              # 模板展开线程池大小
    template_cache={},           # 跨调用共享缓存（None 则新建）
    use_persistent_cache=True,   # 是否加载磁盘缓存（默认 True）
)
```

### `BatchConvertResult.results` 顺序说明

`result.results` **仅含成功项**，顺序与输入**一致**（按 lang 分组、按输入顺序填充）。如需查找特定标题的结果，可自行构建 `dict[title, result]`：

```python
result = convert_many(["钻石", "铁锭", "附魔台"], lang="zh")
by_title = {r.title: r for r in result.results}
md_diamond = by_title.get("钻石")
```

### `MinecraftColorFormatter` 独立 API

低层颜色规范类，可独立使用或子类化：

```python
from minecraft_wiki_mdifier.formatters import MinecraftColorFormatter

f = MinecraftColorFormatter()
md_text = f.clean("&e黄色&r重置")  # '[yellow]黄色[reset]重置'

# 自定义颜色规范（未来扩展）
class HtmlColorFormatter(MinecraftColorFormatter):
    COLORS = {"red": "#ff0000", "blue": "#0000ff"}
    # ...
```

## 依赖

### 必需

- `requests` — MediaWiki API HTTP 客户端
- `beautifulsoup4` — HTML 解析
- `click` — CLI 框架
- `markdownify` — 通用 HTML → Markdown 转换

### 可选

- `tqdm` — `mdifier batch` 进度条；缺则降级为 stderr 文本

## License

MIT
