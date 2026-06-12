# Minecraft Wiki MDifier

将 Minecraft Wiki 页面转换为 AI 助手易读的 Markdown 格式。

## 安装

```bash
pip install -e .
```

## 使用方式

### CLI

```bash
# 转换页面
mdifier "铁锭"

# 输出到文件
mdifier "铁锭" -o iron_ingot.md

# 使用 URL
mdifier "https://zh.minecraft.wiki/铁锭"

# 搜索页面
mdifier search "钻石"

# 批量转换：多个标题 → 独立 .md 文件
mdifier batch -t 钻石 -t 铁锭 -t 附魔台 -o ./out

# 批量转换：从文件读取标题列表（每行一个，# 开头为注释）
mdifier batch -i pages.txt -o ./out --workers 8

# 批量转换：从搜索结果中取前 N 个
mdifier batch --from-search "红石" --search-limit 30 -o ./out
```

### Python 库

```python
from mdifier import convert, convert_many

# 简单转换
md = convert("铁锭")
print(md)

# 批量转换
result = convert_many(["钻石", "铁锭", "附魔台"], max_workers=4)
for r in result.results:
    print(f"=== {r.title} ===")
    print(r.markdown)
if result.failed:
    print(f"失败: {result.failed}")
```

## 功能特点

- **双模式**：CLI（`mdifier`）+ Python 库
- **批量转换**：`mdifier batch` 子命令支持 -t / -i / --from-search
- **跨页模板缓存**：相同模板只请求一次，批量场景大幅节省 HTTP 请求
- **智能获取**：优先 MediaWiki API，HTML 降级抓取
- **模板适配**：合成表、物品信息框、战利品表等 30+ 常见模板自动展开
- **mcui 解析**：合成台、熔炉、织布机、锻造台的图片化 UI 转语义化文本
- **颜色代码**：Minecraft `&e` `&r` 等格式代码转为 `[yellow]` `[reset]` 等语义标签
- **并发优化**：模板展开使用线程池，30+ 模板页面 4.6x 加速

## 模板处理

模板被包裹在 `<template:xxx>` 标记中，内容按格式分类型处理：

| 模板 | 输出 |
|------|------|
| `Infobox`（物品信息框） | 两列 Markdown 表格 |
| `Crafting`（合成表） | 三列：材料 / 配方 / 描述 |
| `LootChest`（战利品表） | 六列：物品 / 来源 / 数量 / 概率等 |
| `mcui`（合成台/熔炉/织布机/锻造台） | 3x3 网格文本 + 物品描述 |
| `Hatnote`、`Quote` | 用 markdownify 转为 Markdown 格式 |
| 其他未识别模板 | 通用 markdownify 转换 |

**输出示例**：

```markdown
### 合成

<template:wikitable start>
| 材料 | 合成 配方 |
| --- | --- |
| 钻石块 | [_|_|_ / _|_|钻石块|_ / _|_|_] -> 钻石x9 |
<template:wikitable end>
```

## 项目结构

```
src/mdifier/
├── __init__.py           # 包初始化，导出 convert/convert_detailed/search
├── lib.py                # 库模式 API
├── cli.py                # CLI 入口（click）
├── convert.py            # 独立转换脚本（可命令行直接运行）
├── search.py             # 独立搜索脚本
├── wiki.py               # MediaWiki API 获取 + HTML 降级
├── parser.py             # Wikitext 解析器（模板/链接/标题）
├── template_expander.py  # 模板展开：HTML 解析 + 格式检测 + mcui 解析
└── converter.py          # Markdown 生成：dict dispatch 渲染
```

### 数据流

1. `WikiFetcher` → MediaWiki API 获取 wikitext
2. `WikiParser` → 解析 AST，提取模板到 `templates` 字典
3. `TemplateExpander` → **并发**调用 API 展开每个模板的渲染 HTML
4. `MarkdownConverter` → 按格式分发到对应渲染器，生成最终 Markdown

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
mdifier "钻石" -o diamond.md

# 多页批量
for page in 钻石 铁锭 附魔台; do
    mdifier "$page" -o "${page}.md"
done
```

## 依赖

- `requests` — MediaWiki API HTTP 客户端
- `beautifulsoup4` — HTML 解析
- `click` — CLI 框架
- `markdownify` — 通用 HTML → Markdown 转换

### 可选依赖

- `tqdm` — `mdifier batch` 进度条；缺则降级为 stderr 文本

## License

MIT
