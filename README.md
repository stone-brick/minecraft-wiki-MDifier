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

# 使用URL
mdifier "https://zh.minecraft.wiki/铁锭"

# 搜索页面
mdifier search "钻石"
```

### Python库

```python
from mdifier import convert

# 简单转换
md = convert("铁锭")
print(md)

# 获取详细信息（包含模板数据）
from mdifier import convert_detailed
result = convert_detailed("铁锭")
print(result.title)      # 页面标题
print(result.markdown)    # Markdown内容
print(result.templates)   # 模板数据
```

## 功能特点

- 支持 CLI 和 Python 库两种使用方式
- 优先使用 MediaWiki API 获取内容，降级到 HTML 抓取
- Wiki 模板（合成表、信息框、进度等）转换为带语言标注的代码块
- 图片保留描述和原始 URL 链接

## 模板处理

各类 Wiki 模板会被转换为代码块格式：

| 原模板 | 输出语言标注 |
|--------|-------------|
| 合成表 | ```mc:crafting |
| 物品信息框 | ```mc:infobox |
| 进度 | ```mc:advancement |
| 其他模板 | ```mc:template |

## 项目结构

```
mdifier/
├── src/mdifier/
│   ├── cli.py          # CLI入口
│   ├── wiki.py         # Wiki页面获取
│   ├── parser.py       # MediaWiki解析器
│   ├── converter.py    # Markdown转换器
│   ├── lib.py          # 库模式API
│   └── templates/      # 模板处理器
│       ├── crafting.py
│       ├── infobox.py
│       ├── progress.py
│       └── common.py
├── tests/
└── pyproject.toml
```

## Claude Code Skill

mdifier 可以作为 Claude Code 的技能（Skill）使用。

### 目录结构

```
.claude/skills/mdifier/
├── SKILL.md           # 技能配置（待创建）
└── scripts/
    ├── convert.py     # 转换脚本
    └── search.py      # 搜索脚本
```

### 使用方式

#### 转换页面
```bash
python .claude/skills/mdifier/scripts/convert.py --title "页面标题" --output 结果.md
```

#### 搜索页面
```bash
python .claude/skills/mdifier/scripts/search.py "搜索关键词"
```

### 脚本参数

**convert.py:**
- `--title`: 页面标题（必需）
- `--output`: 输出文件路径（可选）
- `--lang`: 语言 zh/en（默认zh）
- `--include-templates`: 包含模板数据（可选）

**search.py:**
- `query`: 搜索关键词（位置参数）
- `--num`: 返回数量（默认10）
- `--lang`: 语言（默认zh）

### 示例

```bash
# 转换"钻石"页面
python .claude/skills/mdifier/scripts/convert.py --title "钻石"

# 搜索含"钻石"的内容
python .claude/skills/mdifier/scripts/search.py "钻石"

# 转换并保存到文件
python .claude/skills/mdifier/scripts/convert.py --title "铁锭" --output iron.md

# 搜索英文页面
python .claude/skills/mdifier/scripts/search.py "diamond" --lang en
```

## License

MIT
