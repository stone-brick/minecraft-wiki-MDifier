# Pandoc Filter 探索报告

## 1. 概述

Pandoc Filter 是一种程序，通过 Pandoc 的抽象语法树（AST）对文档进行转换。Pandoc 将输入文档解析为 JSON 格式的 AST，Filter 读取并修改这个 AST，最后输出转换后的文档。

```
输入文档 → Pandoc Parser → JSON AST → Filter 处理 → JSON AST → Pandoc Writer → 输出文档
```

## 2. Python Filter 库对比

### 2.1 pandocfilters（官方库）

- 作者：John MacFarlane（Pandoc 作者）
- 特点：基于 JSON 的低层 API
- 缺点：不够 Pythonic

```python
from pandocfilters import toJSONFilter, Str

def caps(key, value, format, meta):
    if key == 'Str':
        return Str(value.upper())

if __name__ == "__main__":
    toJSONFilter(caps)
```

### 2.2 Panflute（推荐）

- 作者：Sergio Correia
- 特点：更 Pythonic，封装更好，带辅助函数
- 文档：https://panflute.readthedocs.io/

```python
from panflute import *

def increase_header_level(elem, doc):
    if isinstance(elem, Header) and elem.level < 6:
        elem.level += 1

def main(doc=None):
    return run_filter(increase_header_level, doc=doc)

if __name__ == "__main__":
    main()
```

#### Panflute 核心功能

| 功能 | 说明 |
|------|------|
| `run_filter()` | 运行过滤器处理 AST |
| `convert_text()` | 转换文本（类似 pypandoc） |
| `stringify()` | 从元素提取纯文本 |
| `prepare/doc` | 初始化/清理钩子 |

#### 版本兼容性

| panflute 版本 | 支持的 pandoc 版本 |
|---------------|-------------------|
| 2.3.1 | 2.11.0.4 – 3.1.x |
| 2.2.4 | 2.11.0.4 – 2.17.x |
| 2.1.x | 2.11.0.4 – 2.14.x |

当前项目环境：**需验证 pandoc 版本**

## 3. pypandoc 中的 Filter 使用

pypandoc 支持通过 `filters` 参数传递过滤器：

```python
import pypandoc

# 使用外部过滤器
output = pypandoc.convert_text(
    source,
    to='markdown',
    format='mediawiki',
    filters=['pandoc-citeproc']  # 过滤器列表
)

# 配合 extra_args 使用
output = pypandoc.convert_text(
    source,
    to='gfm',
    format='mediawiki',
    extra_args=['--atx-headers'],
    filters=['./my_filter.py']
)
```

**注意**：过滤器必须是可执行文件，pypandoc 会自动调用 Python 解释器运行 `.py` 文件。

## 4.对本项目的潜在意义

### 4.1 当前痛点

1. **MediaWiki 列表标记**：`+` 和 `-` 在转换为 Markdown 后产生混合标记或转义
2. **模板保留**：需要在转换后识别并处理 ` ``` {=mediawiki} ` 块
3. **格式规范化**：GFM vs CommonMark 输出差异

### 4.2 Filter 能做什么

| 场景 | Filter 解决方案 |
|------|---------------|
| 修复列表标记 | 遍历 AST 中的 `BulletList`/`OrderedList`，标准化标记符号 |
| 处理保留的模板块 | 识别 `RawBlock` 元素，提取并处理模板内容 |
| 清理格式 | 规范化链接、图片、代码块等元素的输出格式 |
| 自定义转换 | 在 AST 层面对特定元素进行定制处理 |

### 4.3 实际应用示例

#### 列表修复 Filter

```python
from panflute import *

def fix_mediawiki_lists(elem, doc):
    """
    修复 MediaWiki '+' 和 '-' 列表标记
    Pandoc 将 '+' 转为 '\+'（转义），'-' 可能与列表混淆
    """
    if isinstance(elem, BulletList):
        # 检查并规范化列表标记
        pass
    if isinstance(elem, Str) and elem.text.startswith('\\+'):
        # 移除转义，恢复为普通列表标记
        return Str(elem.text[1:])

def main(doc=None):
    return run_filter(fix_mediawiki_lists, doc=doc)

if __name__ == "__main__":
    main()
```

#### 使用方式

```python
import pypandoc

output = pypandoc.convert_text(
    wikitext,
    to='gfm',
    format='mediawiki',
    filters=['./filters/fix_lists.py']
)
```

## 5. 项目集成建议

### 5.1 架构考量

当前项目流程：
```
Wikitext → pypandoc.convert_text → 模板块替换 → Markdown
                ↓
          当前：无 Filter
```

引入 Filter 后：
```
Wikitext → pypandoc.convert_text(+filters) → 处理后的 AST → 模板块替换 → Markdown
```

### 5.2 推荐方案

**方案 A：最小改动**
- 在现有流程中增加后处理 Filter
- Filter 负责修复列表标记等特定问题
- 优点：不影响现有架构

**方案 B：完整集成**
- 将 pypandoc 替换为 panflute 的 `convert_text`
- 在一个流程中完成转换和过滤
- 优点：更灵活，可深度定制

### 5.3 依赖增加

```toml
# pyproject.toml
dependencies = [
    ...
    "panflute>=2.0",
]
```

## 6. 已知限制

1. **性能开销**：Filter 增加了 AST 序列化/反序列化开销
2. **Pandoc 版本依赖**：需要匹配 panflute 和 pandoc 版本
3. **调试复杂**：Filter 问题难以追踪

## 7. 下一步建议

1. **验证环境**：`pandoc --version` 和 `pip show panflute` 确认版本兼容
2. **小规模测试**：用 panflute 写一个简单的列表修复 Filter 测试
3. **性能基准**：对比有无 Filter 的转换性能
4. **评估收益**：权衡 Filter 带来的复杂度和实际收益

---

报告生成日期：2026-06-29
