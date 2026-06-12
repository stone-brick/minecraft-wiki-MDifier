# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

将 Minecraft Wiki 页面转换为 AI 助手易读的 Markdown 格式。

## 常用命令

```bash
# 安装
pip install -e .

# CLI使用
mdifier "铁锭"
mdifier "铁锭" -o iron.md
mdifier search "钻石"

# 直接运行脚本
python src/mdifier/convert.py --title "钻石" --output diamond.md
python src/mdifier/search.py "钻石" --num 5
```

## 架构

```
src/mdifier/
├── wiki.py              # MediaWiki API获取（优先）和HTML降级抓取
├── parser.py           # Wikitext解析器，逐字符提取模板/链接/标题
├── template_expander.py # 通过 API 展开模板获取渲染后HTML
├── converter.py        # 将解析结果转换为 Markdown
├── lib.py              # 对外API
├── cli.py              # CLI入口（click）
├── convert.py          # 独立转换脚本
└── search.py          # 独立搜索脚本
```

### 数据流

1. `WikiFetcher` 通过 MediaWiki API 获取 wikitext
2. `WikiParser` 解析 wikitext，提取模板存入 `templates` 字典
3. `TemplateExpander` 对每个模板调用 `action=parse&text=` API 获取渲染后HTML
4. `MarkdownConverter` 生成 Markdown，模板被包裹在 `<template:class start/end>` 标记中

### 模板展开机制

```python
# 模板 {{Hatnote|text}} 展开后返回
{
    "class": "hatnote",
    "text": "渲染后的文本内容",
    "html": "原始HTML"
}
```

## 开发注意

- Python 版本: >=3.13
- 依赖: requests, beautifulsoup4, click
- 模板解析使用逐字符方法而非正则，支持跨行模板
- API展开失败时返回原始参数的简单描述