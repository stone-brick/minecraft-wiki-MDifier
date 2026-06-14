<div align="center">

# ⚡ Minecraft Wiki MDifier

Convert Minecraft Wiki pages to AI-friendly Markdown

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.13+-green.svg)](https://python.org)

**[中文](./README.md)** · **[日本語](./README-ja.md)**

</div>

## Installation

**Requires Python >= 3.13**, dependencies: `requests`, `beautifulsoup4`, `click`, `markdownify`.

```bash
pip install -e .
```

### PATH Setup

The `mdifier` command is installed to Python's Scripts directory. If not found:

**Windows (Git Bash / PowerShell)**:
```bash
# Find Scripts path
python -c "import sysconfig; print(sysconfig.get_paths()['scripts'])"
# Add to PATH (replace with actual path)
export PATH="$PATH:/d/Program Files/Python/Python313/Scripts"
# Permanent: add to ~/.bashrc
```

**macOS / Linux**:
```bash
# Usually installed to ~/.local/bin
export PATH="$PATH:$HOME/.local/bin"
# Or: python -m mdifier.cli (cross-platform equivalent)
```

Verify:
```bash
mdifier --version
# Or: python -m mdifier.cli --version
```

### Path Best Practices (for AI assistants)

`-o` and `-i` path behavior **varies by shell**. Use **relative paths** to avoid confusion:

| Path form | PowerShell | Git Bash | Recommendation |
|----------|------------|----------|------------------|
| `output/x.md` (relative) | cwd | cwd | 🥇 Consistent |
| `D:/tests/x.md` (Win absolute) | D:\tests\x.md | D:\tests\x.md | 🥈 Works both |
| `/tests/x.md` (Unix absolute) | **D:\tests\x.md** (literal) | D:\Program Files\Git\tests (MSYS translation) | ❌ Inconsistent |

**Recommended**:
```bash
cd ~/wiki && mdifier convert "Iron Ingot" -o output/iron.md
mkdir -p output && mdifier batch -t Diamond -t Iron_Ingot -o output/
```

### Exit Codes (BSD sysexits)

| Code | Name | Meaning |
|------|------|---------|
| 0 | Success | All OK |
| 64 (`EX_USAGE`) | Command error | Bad lang/format args |
| 65 (`EX_DATAERR`) | Data error | Page not found, partial batch failure |
| 70 (`EX_SOFTWARE`) | Software error | Unexpected exception |
| 74 (`EX_IOERR`) | I/O error | File write/directory creation failed |
| 75 (`EX_TEMPFAIL`) | Temp failure | Network/API temporarily unavailable |
| 77 (`EX_NOPERM`) | Permission error | No write permission |

## Usage

### CLI

```bash
# Convert page (English wiki default)
mdifier convert "Iron Ingot"

# Chinese wiki
mdifier convert "铁锭" --lang zh -o iron.md

# Full JSON output (includes templates)
mdifier convert "Iron Ingot" --detail

# Using URLs (auto-detects language)
mdifier convert "https://minecraft.wiki/wiki/Iron_Ingot"
mdifier convert "https://zh.minecraft.wiki/铁锭"

# Search
mdifier search "diamond" --lang en
mdifier search "钻石" -n 20

# Batch convert: multiple titles → separate .md files
mdifier batch -t Diamond -t Iron_Ingot -o ./out
mdifier batch -i pages.txt -o ./out --workers 8

# Cache management
mdifier cache info    # Show cache stats
mdifier cache clear   # Clear cache (interactive; -y to skip prompt)
mdifier cache prune   # Remove expired entries only

# Custom template markers
mdifier batch -t Diamond --marker-format '<details><summary>{name}</summary>/</details>'
```

Without pip or if `mdifier` not found:
```bash
python -m mdifier.cli convert "Iron Ingot"
python -m mdifier.cli search "diamond"
```

### Python Library

```python
from mdifier import convert, convert_detailed, convert_many, search

# Simple convert (English wiki default)
md = convert("Iron Ingot")

# Chinese wiki
md_zh = convert("铁锭", lang="zh")

# Detailed mode returns ConvertResult (CLI equivalent: --detail)
result = convert_detailed("Iron Ingot")
print(f"Title: {result.title}")
print(f"Source: {result.source}")  # "api" or "html"
print(f"Templates: {result.templates}")  # Non-empty dict with expanded template data

# Shared cache across calls (same process, no disk writes)
shared_cache = {}
convert("Diamond", template_cache=shared_cache)
convert("Iron Ingot", template_cache=shared_cache)

# Batch convert
result = convert_many(["Diamond", "Iron Ingot", "Enchantment Table"], max_workers=4)
for r in result.results:
    print(f"=== {r.title} ===")
    print(r.markdown)
if result.failed:
    print(f"Failed: {result.failed}")

# Progress callback
def on_progress(done, total, title):
    print(f"[{done}/{total}] {title}")
result = convert_many(["Diamond", "Iron Ingot"], on_progress=on_progress)

# Search
results = search("diamond", lang="en")
for r in results[:5]:
    print(f"{r['title']}: {r['description']} ({r['url']})")
```

### URL Auto-Detection

| URL pattern | Detected as |
|-------------|-------------|
| `https://minecraft.wiki/wiki/Iron_Ingot` | en |
| `https://en.minecraft.wiki/wiki/Diamond` | en |
| `https://zh.minecraft.wiki/wiki/铁锭` | zh |
| `https://zh.minecraft.wiki/铁锭` (no /wiki/) | zh |
| `Diamond` (plain title) | Uses `--lang` default |

### Error Handling

```python
# Single-page convert raises InvalidInputError (inherits from ValueError)
try:
    md = convert("nonexistent_page")
except InvalidInputError as e:
    print(f"Failed: {e}")

# Batch doesn't raise, aggregates failures in result.failed
result = convert_many(["Diamond", "nonexistent"])
for title, err in result.failed:
    print(f"  Failed: {title}: {err}")

# Unsupported language raises InvalidInputError
try:
    convert("X", lang="xx")
except InvalidInputError as e:
    print(e)  # "Unsupported language: xx. Available: ['zh', 'en']"
```

**Exception hierarchy**:

| Exception | Base classes | Meaning |
|-----------|--------------|---------|
| `MdifierError` | `Exception` | Base class |
| `InvalidInputError` | `MdifierError`, `ValueError` | User input error |
| `FetchError` | `MdifierError`, `requests.RequestException` | Network error base |
| `NetworkError` | `FetchError` | Connection failed/timeout |
| `WikiAPIError` | `FetchError` | API returned error structure |
| `PageNotFoundError` | `FetchError` | Page not found |
| `BucketAPIError` | `MdifierError` | Bucket API call failed |
| `CacheError` | `MdifierError`, `OSError` | Cache read/write failed |

## Features

- **Dual mode**: CLI (`mdifier`) + Python library
- **Multi-language**: Built-in `zh` (zh.minecraft.wiki) and `en` (minecraft.wiki)
- **Batch convert**: `mdifier batch` supports `-t` / `-i` / `--from-search`
- **Cross-language batch**: Title list can mix zh/en pages, auto-grouped by language
- **Persistent template cache**: Same templates requested once, shared across runs (**5.4x speedup**)
- **Cache management**: `mdifier cache info/clear/prune`
- **Auto PascalCase**: Only for all-lowercase names without spaces/hyphens
- **Unexpanded report**: Reports missing templates at batch end
- **Configurable markers**: Custom `<template:xxx>` marker formats
- **Batch cancellation**: `MarkdownConverter.cancel()` interrupts large batches
- **Smart fetching**: MediaWiki API first, HTML fallback
- **Network retry**: HTTP GET auto-retries 3x (exponential backoff 0.5s/1s/2s) for 5xx/429
- **Template adaptation**: 30+ common templates auto-expanded
- **mcui parsing**: Crafting table/furnace/loom/smithing table image-UI to semantic text
- **Color codes**: Minecraft `&e` `&r` etc. converted to `[yellow]` `[reset]` etc.
- **Concurrency**: Template expansion uses thread pool, single page 4.6x speedup

## Template Processing

Templates are wrapped in `:::{name}` markers, content type determines rendering:

| Template | Output |
|---------|--------|
| `Infobox` (item info box) | Two-column Markdown table |
| `Crafting` (crafting table) | Three columns: Materials / Recipe / Description |
| `LootChest` (loot table) | Six columns: Item / Source / Quantity / Chance etc. |
| `mcui` (crafting/furnace/loom/smithing) | 3x3 grid text + item descriptions |
| `Hatnote`, `Quote` | Converted via markdownify |
| Other unrecognized | Generic markdownify conversion |
| Expansion failed (API error) | Fallback text `[template: k=v]`, marked as `class="error"` |

**Example output**:

```markdown
### Crafting

:::Crafting
| Ingredients | Crafting recipe |
| --- | --- |
| Diamond Block | [Diamond|Diamond|Diamond / Diamond|Diamond|Diamond / Diamond|Diamond|Diamond] -> Diamondx9 |
:::
```

## Performance & Caching

### Cache Mechanism

Template expansion results auto-persisted to disk:

- **Location**: `~/.cache/mdifier/templates.json`
- **Size**: ~1 MB / 1000 templates
- **TTL**: 7 days (auto-expired)
- **Shared**: Cross-process, cross-run, cross-project

### Performance Data

| Scenario | Time |
|---------|------|
| First run (cold cache) | ~6s |
| Second run (cache hit) | ~1s |
| **Speedup** | **5.4x** |

### Custom Template Markers

Can be changed to HTML `details` style. `open` and `close` configured independently:

```python
from mdifier.converter import MarkdownConverter

c = MarkdownConverter()
c.template_marker_open = ":::{name}"
c.template_marker_close = ":::"

# Or HTML style
c.template_marker_open = "<details><summary>{name}</summary>"
c.template_marker_close = "</details>"
```

CLI uses `--marker-format` (format: `open/close`, separated by `/`, `{name}` is placeholder):

```bash
mdifier batch -t Diamond --marker-format '<details><summary>{name}</summary>/</details>'
```

### Batch Cancellation

Get converter reference via `converter_factory` param, call `cancel()` from another thread:

```python
import threading
from mdifier import convert_many
from mdifier.converter import MarkdownConverter

c = MarkdownConverter(lang='en')
threading.Timer(0.5, c.cancel).start()
convert_many(['Diamond', 'Iron Ingot', 'Enchantment Table'],
             converter_factory=lambda l, cache: c)

print(c.is_cancelled())          # True
print(c.unresolved_templates)    # frozenset({'HistoryTable', ...})
```

### Output File Naming

Files named via `_slug()`:
- Invalid filename chars (`\ / : * ? " < > |`) → `_`
- Spaces → `_`
- Emoji/high Unicode → removed
- Empty title fallback → `untitled`
- Conflicts: auto-suffix `-2`, `-3`, etc.; >999 conflicts use uuid prefix

### Input File Format (`-i`)

```
# Comment lines (# prefix)
Diamond
Iron Ingot
# Empty lines auto-skipped
```

### Shared Cache (No Persistence)

Single-page `convert()` also supports passing `template_cache` for same-process sharing:

```python
from mdifier import convert

shared = {}
convert("Diamond", template_cache=shared)  # 24 template expansions
convert("Iron Ingot", template_cache=shared)  # +17 new, 24 shared
```

**Difference from disk cache**:
- `template_cache` param: In-process only, no disk writes
- Disk cache (`~/.cache/mdifier/`): Cross-process, cross-run
- `convert_many()` uses disk cache; doesn't write single-call intermediate cache

### Cache Commands

| Command | Behavior | Use Case |
|---------|-----------|---------|
| `mdifier cache info` | Read-only stats | View cache status |
| `mdifier cache clear` | Delete entire cache file | Wiki major update, force rebuild |
| `mdifier cache prune` | Keep unexpired (< 7 days), delete expired | Routine maintenance |

`cache clear` prompts for confirmation by default (use `-y` to skip).

## Project Structure

```
src/mdifier/
├── __init__.py           # Exports convert/convert_detailed/convert_many/search
├── lib.py                # Library mode API (with convert_many)
├── cli.py                # CLI entry (click, with batch/cache subcommands)
├── wiki.py               # MediaWiki API fetch + HTML fallback
├── parser.py             # Wikitext parser (templates/links/headings)
├── template_expander.py   # Template expansion: action=bucket or action=parse + format detection
├── formatters.py         # Minecraft color codes → semantic labels
├── converter.py          # Markdown generation: dict dispatch rendering
└── cache.py              # Template expansion cache persistence
```

### Data Flow

1. `WikiFetcher` → MediaWiki API fetches wikitext
2. `WikiParser` → Parses AST, extracts templates to `templates` dict
3. `TemplateExpander` → For Lua data query templates (Trade uses etc.), tries `action=bucket` first, falls back to `action=parse`
4. `MarkdownConverter` → Dispatches to appropriate renderer, generates final Markdown
5. Cross-run: `get_or_load_persistent_cache()` lazy-loads disk cache singleton; batch only `save_cache()` once at end

## Development

### Install Dev Dependencies

```bash
pip install -e ".[dev]"
pre-commit install
```

### Run Ruff

```bash
ruff check .
```

Or via pre-commit (auto-runs on commit):
```bash
pre-commit run --all-files
```

### Manual Testing

```bash
mdifier convert "Diamond" -o diamond.md
mdifier cache info
mdifier cache clear -y
```

## License

MIT
