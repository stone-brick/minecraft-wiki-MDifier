<div align="center">

# ⚡ Minecraft Wiki MDifier

Convert Minecraft Wiki pages to AI-friendly Markdown

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)

**[中文](./README.md)** · **[日本語](./README-ja.md)**

</div>

## Installation

**Requires Python >= 3.11**

```bash
# Install from PyPI (recommended)
pip install minecraft-wiki-mdifier

# Local development
pip install -e .
```

Verify:

```bash
mdifier --version
# Or: python -m minecraft_wiki_mdifier.cli --version
```

## Quick Start

```bash
# Convert page (English wiki default)
mdifier convert "Iron Ingot"

# Save to file
mdifier convert "Iron Ingot" -o iron.md

# Chinese wiki
mdifier convert "铁锭" --lang zh -o iron.md

# Auto-detect language from URL
mdifier convert "https://minecraft.wiki/wiki/Iron_Ingot"
mdifier convert "https://zh.minecraft.wiki/铁锭"

# Search
mdifier search "diamond"
mdifier search "钻石" --lang zh

# Batch convert
mdifier batch -t Diamond -t Iron_Ingot -o ./out
mdifier batch -i pages.txt -o ./out --workers 8
mdifier batch -t Diamond --no-markers  # Disable template markers

# Cache management
mdifier cache info
mdifier cache clear -y   # Clear cache
mdifier cache prune       # Remove expired entries
```

## CLI Reference

### convert

```bash
mdifier convert "TITLE_OR_URL" [-o OUTPUT] [--lang {zh|en|ja}] [--detail]
```

| Option | Description |
|--------|-------------|
| `-o, --output` | Output file path |
| `-l, --lang` | Language (default en) |
| `--detail` | Full JSON output (title, markdown, source, templates) |

### search

```bash
mdifier search "QUERY" [-l {zh|en|ja}] [-n NUM]
```

| Option | Description |
|--------|-------------|
| `-n NUM` | Number of results (default 10) |

### batch

```bash
mdifier batch [-t TITLE] [-i FILE] [--from-search QUERY] [-o DIR] [--workers N] [--no-progress] [--marker-format FORMAT]
```

| Option | Description |
|--------|-------------|
| `-t, --title` | Page title (can be used multiple times) |
| `-i, --input-file` | Title list file (one per line, `#` for comments) |
| `--from-search` | Get titles from search |
| `--search-limit` | Max results for `--from-search` |
| `-o, --output-dir` | Output directory; None prints to stdout |
| `--workers` | Concurrent page fetches (default 4) |
| `--no-progress` | Disable progress bar |
| `--marker-format` | Custom marker format `open/close` (`{name}` = template class name) |

### cache

```bash
mdifier cache info|clear|prune
```

- `info` — Stats (path, size, entries, expired count, timestamps)
- `clear` — Clear entire cache (`-y` skips confirmation)
- `prune` — Remove expired entries only

## Python API

```python
from minecraft_wiki_mdifier import convert, convert_detailed, convert_many, search

# Simple convert
md = convert("Iron Ingot")

# Detailed mode
result = convert_detailed("Iron Ingot")
print(result.title)      # Page title
print(result.source)    # "api" or "html"
print(result.templates) # Template data dict

# Batch convert
result = convert_many(["Diamond", "Iron Ingot", "Enchantment Table"], max_workers=4)
for r in result.results:
    print(f"=== {r.title} ===")
if result.failed:
    print(f"Failed: {result.failed}")
if result.unresolved:
    print(f"Unexpanded templates: {result.unresolved}")

# Search
results = search("diamond", lang="en")
for r in results[:5]:
    print(f"{r['title']}: {r['description']}")
```

### URL Auto-Detection

| Input | Detected as |
|-------|-------------|
| `https://minecraft.wiki/wiki/Iron_Ingot` | en |
| `https://zh.minecraft.wiki/wiki/铁锭` | zh |
| `https://ja.minecraft.wiki/wiki/鉄インゴット` | ja |
| Plain title | Uses `lang` param (default en) |

### Cross-Language Batch

```python
items = [
    "Diamond",                                     # en
    "https://zh.minecraft.wiki/wiki/钻石",         # zh (URL detected)
    "鉄インゴット",                                 # ja (default lang)
]
result = convert_many(items, lang="en")
```

## Advanced Usage

### Custom Template Markers

```python
from minecraft_wiki_mdifier.converter import MarkdownConverter

c = MarkdownConverter()
c.template_marker_open = '<details><summary>{name}</summary>'
c.template_marker_close = '</details>'
```

CLI: `--marker-format`:

```bash
mdifier batch -t Diamond --marker-format '<details><summary>{name}</summary>/</details>'
```

### Batch Cancellation

```python
import threading
from minecraft_wiki_mdifier.converter import MarkdownConverter

c = MarkdownConverter(lang='en')
threading.Timer(0.5, c.cancel).start()  # Cancel after 0.5s

convert_many(['Diamond', 'Iron Ingot', 'Enchantment Table'],
             converter_factory=lambda l, cache: c)

print(c.is_cancelled())       # True
print(c.unresolved_templates) # frozenset({'HistoryTable', ...})
```

### Shared Cache Across Calls

```python
shared = {}
convert("Diamond", template_cache=shared)   # 24 template expansions
convert("Iron Ingot", template_cache=shared) # +17 new, 24 shared
```

Note: `template_cache` is in-process only, no disk writes; disk cache (`~/.cache/mdifier/`) is shared across processes.

### Color Codes

```python
from minecraft_wiki_mdifier.formatters import MinecraftColorFormatter

f = MinecraftColorFormatter()
f.clean("&eYellow&rReset")  # '[yellow]Yellow[reset]Reset'
```

## Template Processing

Templates are wrapped in `:::{name}` markers, content type determines rendering:

| Template | Output |
|---------|--------|
| `Infobox` | Two-column Markdown table |
| `Crafting` | Three columns: Materials / Recipe / Description |
| `LootChest` | Six columns: Item / Source / Quantity / Chance etc. |
| `mcui` (crafting/furnace/loom/smithing) | 3x3 grid text + item descriptions |
| `Hatnote`, `Quote` | Converted via markdownify |
| Unrecognized | Generic markdownify conversion |
| Expansion failed | Fallback `[template: k=v]`, marked `class="error"` |

Some templates (Trade uses, Crafting usage, etc.) depend on Lua Bucket database, queried via `action=bucket` API.

## Cache

- **Location**: `~/.cache/mdifier/templates.json`
- **TTL**: 7 days
- **Shared**: Cross-process, cross-run
- **Speedup**: First run ~6s, second ~1s (**5.4x**)

Python API:

```python
from minecraft_wiki_mdifier.cache import cache_info, clear_cache

info = cache_info()
if info["size_mb"] > 100:
    clear_cache()
```

## Error Handling

### Python Exceptions

```python
from minecraft_wiki_mdifier import convert, InvalidInputError

try:
    md = convert("nonexistent_page")
except InvalidInputError as e:  # inherits from ValueError
    print(f"Failed: {e}")
```

**Exception hierarchy**:

```
MdifierError
├── InvalidInputError (ValueError)
├── FetchError (requests.RequestException)
│   ├── NetworkError
│   ├── WikiAPIError
│   └── PageNotFoundError
├── BucketAPIError
└── CacheError (OSError)
```

### CLI Exit Codes

| Code | Name | Meaning |
|------|------|---------|
| 0 | Success | All OK |
| 64 | `EX_USAGE` | Command error |
| 65 | `EX_DATAERR` | Data error (page not found, partial batch failure) |
| 70 | `EX_SOFTWARE` | Software error |
| 74 | `EX_IOERR` | I/O error |
| 75 | `EX_TEMPFAIL` | Network temp failure |
| 77 | `EX_NOPERM` | Permission error |

## Multi-Language

Built-in `zh` (zh.minecraft.wiki), `en` (minecraft.wiki), and `ja` (ja.minecraft.wiki).

**Note**: ja wiki's Bucket i18n fields contain Chinese content; the program does not translate by default, outputting English text as-is.

## Project Structure

```
src/minecraft_wiki_mdifier/
├── __init__.py           # Public API exports
├── lib.py                # convert / convert_many / search
├── cli.py                # CLI entry (click)
├── wiki.py               # MediaWiki API fetch + HTML fallback
├── parser.py             # Wikitext parser
├── template_expander.py  # Template expansion (bucket/parse)
├── formatters.py         # Minecraft color code formatter
├── converter.py          # Markdown generation
├── cache.py              # Template cache persistence
├── exceptions.py         # Exception hierarchy
├── _session.py           # HTTP Session factory
└── _validators.py        # Language validator
```

**Data flow**:

1. `WikiFetcher` → MediaWiki API fetches wikitext
2. `WikiParser` → Parses AST, extracts templates
3. `TemplateExpander` → Prefers `action=bucket`, falls back to `action=parse`
4. `MarkdownConverter` → Dispatches to renderer, generates Markdown

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Lint
ruff check .

# pre-commit (auto-runs on commit)
pre-commit install
pre-commit run --all-files
```

## Dependencies

**Required**: requests, beautifulsoup4, click, markdownify

**Optional**: tqdm (progress bar for `mdifier batch`; absent → stderr text fallback)

## License

MIT