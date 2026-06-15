<div align="center">

# ⚡ Minecraft Wiki MDifier

Minecraft Wiki のページを AI に優しい Markdown に変換

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.13+-green.svg)](https://python.org)

**[中文](./README.md)** · **[English](./README-en.md)**

</div>

## インストール

**Python >= 3.13** が必要です。依存ライブラリ: `requests`, `beautifulsoup4`, `click`, `markdownify`.

```bash
# PyPI からインストール（推奨）
pip install minecraft-wiki-mdifier

# ローカル開発用（編集可能）
pip install -e .
```

### PATH 設定

`mdifier` コマンドは Python の Scripts ディレクトリにインストールされます。見つからない場合：

**Windows (Git Bash / PowerShell)**:
```bash
# Scripts パスを確認
python -c "import sysconfig; print(sysconfig.get_paths()['scripts'])"
# PATH に追加（実際のパスに置き換えてください）
export PATH="$PATH:/d/Program Files/Python/Python313/Scripts"
# 永続化: ~/.bashrc に追加
```

**macOS / Linux**:
```bash
# 通常 ~/.local/bin にインストールされます
export PATH="$PATH:$HOME/.local/bin"
# または: python -m minecraft_wiki_mdifier.cli（クロスプラットフォーム）
```

確認:
```bash
mdifier --version
# または: python -m minecraft_wiki_mdifier.cli --version
```

### Path のベストプラクティス（AI アシスタント向け）

`-o` と `-i` のパス動作はシェルによって異なります。**相対パス**を使用して混乱を避ける：

| パスの形式 | PowerShell | Git Bash | 推奨度 |
|-----------|------------|----------|--------|
| `output/x.md` (相対) | cwd | cwd | 🥇 一貫性あり |
| `D:/tests/x.md` (Win 絶対) | D:\tests\x.md | D:\tests\x.md | 🥈 両対応 |
| `/tests/x.md` (Unix 絶対) | **D:\tests\x.md** (リテラル) | D:\Program Files\Git\tests (MSYS 変換) | ❌ 不一貫 |

**推奨**:
```bash
cd ~/wiki && mdifier convert "Iron Ingot" -o output/iron.md
mkdir -p output && mdifier batch -t Diamond -t Iron_Ingot -o output/
```

### 終了コード (BSD sysexits)

| コード | 名前 | 意味 |
|------|------|------|
| 0 | Success | 正常終了 |
| 64 (`EX_USAGE`) | Command error | lang/format 引数エラー |
| 65 (`EX_DATAERR`) | Data error | ページが見つからない、バッチ一部失敗 |
| 70 (`EX_SOFTWARE`) | Software error | 予期しない例外 |
| 74 (`EX_IOERR`) | I/O error | ファイル書き込み/ディレクトリ作成失敗 |
| 75 (`EX_TEMPFAIL`) | Temp failure | ネットワーク/API一時的に利用不可 |
| 77 (`EX_NOPERM`) | Permission error | 書き込み権限なし |

## 使い方

### CLI

```bash
# ページを変換（英語 wiki デフォルト）
mdifier convert "Iron Ingot"

# 中国語 wiki
mdifier convert "鉄锭" --lang zh -o iron.md

# 日本語 wiki
mdifier convert "鉄インゴット" --lang ja -o iron.md

# 完全な JSON 出力（テンプレートを含む）
mdifier convert "Iron Ingot" --detail

# URL を使用（言語自動検出）
mdifier convert "https://minecraft.wiki/wiki/Iron_Ingot"
mdifier convert "https://ja.minecraft.wiki/wiki/鉄インゴット"

# 検索
mdifier search "diamond" --lang en
mdifier search "ダイヤモンド" -n 20

# バッチ変換: 複数タイトル → 別々の .md ファイル
mdifier batch -t Diamond -t Iron_Ingot -o ./out
mdifier batch -i pages.txt -o ./out --workers 8

# キャッシュ管理
mdifier cache info    # キャッシュ統計を表示
mdifier cache clear   # キャッシュをクリア（確認付き、-y でスキップ）
mdifier cache prune   # 期限切れエントリのみ削除

# カスタムテンプレートマーカー
mdifier batch -t Diamond --marker-format '<details><summary>{name}</summary></details>'
```

pip がない場合、または `mdifier` が見つからない場合:
```bash
python -m minecraft_wiki_mdifier.cli convert "Iron Ingot"
python -m minecraft_wiki_mdifier.cli search "diamond"
```

### Python ライブラリ

```python
from minecraft_wiki_mdifier import convert, convert_detailed, convert_many, search

# 简单変換（英語 wiki デフォルト）
md = convert("Iron Ingot")

# 中国語 wiki
md_zh = convert("鉄锭", lang="zh")

# 日本語 wiki
md_ja = convert("鉄インゴット", lang="ja")

# 詳細モードは ConvertResult を返す（CLI の --detail に相当）
result = convert_detailed("Iron Ingot")
print(f"Title: {result.title}")
print(f"Source: {result.source}")  # "api" または "html"
print(f"Templates: {result.templates}")  # 展開済みテンプレートデータ

# 呼び出し間でキャッシュを共有（同じプロセス、ディスク書き込みなし）
shared_cache = {}
convert("Diamond", template_cache=shared_cache)
convert("Iron Ingot", template_cache=shared_cache)

# バッチ変換
result = convert_many(["Diamond", "Iron Ingot", "Enchantment Table"], max_workers=4)
for r in result.results:
    print(f"=== {r.title} ===")
    print(r.markdown)
if result.failed:
    print(f"Failed: {result.failed}")

# 進捗コールバック
def on_progress(done, total, title):
    print(f"[{done}/{total}] {title}")
result = convert_many(["Diamond", "Iron Ingot"], on_progress=on_progress)

# 検索
results = search("diamond", lang="en")
for r in results[:5]:
    print(f"{r['title']}: {r['description']} ({r['url']})")
```

### URL 自動検出

| URL パターン | 検出結果 |
|-------------|----------|
| `https://minecraft.wiki/wiki/Iron_Ingot` | en |
| `https://en.minecraft.wiki/wiki/Diamond` | en |
| `https://ja.minecraft.wiki/wiki/鉄インゴット` | ja |
| `https://zh.minecraft.wiki/wiki/鉄锭` | zh |
| `https://zh.minecraft.wiki/鉄锭` (/wiki/ なし) | zh |
| `Diamond` (タイトルだけ) | `--lang` デフォルトを使用 |

### エラーハンドリング

```python
# 1 ページ変換は InvalidInputError をスロー（ValueError を継承）
try:
    md = convert("nonexistent_page")
except InvalidInputError as e:
    print(f"Failed: {e}")

# バッチはスローせず、結果.failed に失敗を集約
result = convert_many(["Diamond", "nonexistent"])
for title, err in result.failed:
    print(f"  Failed: {title}: {err}")

# サポートされていない言語は InvalidInputError をスロー
try:
    convert("X", lang="xx")
except InvalidInputError as e:
    print(e)  # "Unsupported language: xx. Available: ['zh', 'en', 'ja']"
```

**例外階層**:

| 例外 | 基底クラス | 意味 |
|------|----------|------|
| `MdifierError` | `Exception` | 基底クラス |
| `InvalidInputError` | `MdifierError`, `ValueError` | ユーザー入力エラー |
| `FetchError` | `MdifierError`, `requests.RequestException` | ネットワークエラーの基底 |
| `NetworkError` | `FetchError` | 接続失敗/タイムアウト |
| `WikiAPIError` | `FetchError` | API がエラー構造を返した |
| `PageNotFoundError` | `FetchError` | ページが見つからない |
| `BucketAPIError` | `MdifierError` | Bucket API 呼び出し失敗 |
| `CacheError` | `MdifierError`, `OSError` | キャッシュ読み書き失敗 |

## 機能

- **デュアルモード**: CLI (`mdifier`) + Python ライブラリ
- **多言語対応**: 組み込みの `zh`（zh.minecraft.wiki）、`en`（minecraft.wiki）、`ja`（ja.minecraft.wiki）
  - 注意：ja wiki の Bucket i18n フィールドには中国語のデータが含まれており、プログラムはデフォルトで翻訳せず、英語原文を出力します
- **バッチ変換**: `mdifier batch` は `-t` / `-i` / `--from-search` をサポート
- **言語横断バッチ**: タイトルリストは zh/en/ja を混在可能、自动グループ化
- **永続テンプレートキャッシュ**: 同じテンプレートは一度만 요청され、実行間で共有（**5.4x 高速化**）
- **キャッシュ管理**: `mdifier cache info/clear/prune`
- **自動 PascalCase**: スペース/ハイフンがない全て小文字名のみ
- **未展開レポート**: バッチ終了時に欠落テンプレートを報告
- **設定可能なマーカー**: カスタム `:::{name}` マーカー形式
- **バッチキャンセル**: `MarkdownConverter.cancel()` で大規模バッチを中断
- **スマート取得**: MediaWiki API優先、HTML フォールバック
- **ネットワークリトライ**: HTTP GET は 5xx/429 時に3回自動リトライ（指数バックオフ 0.5s/1s/2s）
- **テンプレート適応**: 30+ 個の共通テンプレートが自動展開
- **mcui 解析**: 作業台/炉/織機/鍛造台の画像UIを意味テキストに変換
- **カラーコード**: Minecraft `&e` `&r` などを `[yellow]` `[reset]` などに変換
- **並行処理**: テンプレート展開はスレッドプールを使用、1 ページ 4.6x 高速化

## テンプレート処理

テンプレートは `:::{name}` マーカーでラップされ、内容タイプが描画方法を決定：

| テンプレート | 出力 |
|------------|------|
| `Infobox` (アイテム情報ボックス) | 2列 Markdown テーブル |
| `Crafting` (作業台) | 3列: 材料 / レシピ / 説明 |
| `LootChest` (的战利品テーブル) | 6列: アイテム / ソース / 量 / 確率など |
| `mcui` (作業台/炉/織機/鍛造台) | 3x3 グリッドテキスト + アイテム説明 |
| `Hatnote`, `Quote` | markdownify で変換 |
| その他認識不可 | 汎用 markdownify 変換 |
| 展開失敗 (API エラー) | フォールバックテキスト `[template: k=v]`、class="error" でマーク |

**出力例**:

```markdown
### Crafting

:::Crafting
| Ingredients | Crafting recipe |
| --- | --- |
| Diamond Block | [Diamond|Diamond|Diamond / Diamond|Diamond|Diamond / Diamond|Diamond|Diamond] -> Diamondx9 |
:::
```

## パフォーマンスとキャッシュ

### キャッシュ仕組み

テンプレート展開結果は自動的にディスクに永続化：

- **場所**: `~/.cache/mdifier/templates.json`
- **サイズ**: 約 1 MB / 1000 テンプレート
- **TTL**: 7 日間（自動期限切れ）
- **共有**: プロセス間、実行間、プロジェクト間

### パフォーマンスデータ

| シナリオ | 時間 |
|---------|------|
| 初回実行（冷たいキャッシュ） | 約 6 秒 |
| 2 回目実行（キャッシュヒット） | 約 1 秒 |
| **高速化** | **5.4x** |

### カスタムテンプレートマーカー

HTML `details` スタイルに変更可能。`open` と `close` は個別に設定可能：

```python
from minecraft_wiki_mdifier.converter import MarkdownConverter

c = MarkdownConverter()
c.template_marker_open = ":::{name}"
c.template_marker_close = ":::"

# または HTML スタイル
c.template_marker_open = "<details><summary>{name}</summary>"
c.template_marker_close = "</details>"
```

CLI は `--marker-format` を使用（形式: `open/close`、区切り文字 `/`、`{name}` はプレースホルダー）：

```bash
mdifier batch -t Diamond --marker-format '<details><summary>{name}</summary></details>'
```

### バッチキャンセル

`converter_factory` パラメータで converter 参照を取得、別のスレッドから `cancel()` を呼び出し：

```python
import threading
from minecraft_wiki_mdifier import convert_many
from minecraft_wiki_mdifier.converter import MarkdownConverter

c = MarkdownConverter(lang='en')
threading.Timer(0.5, c.cancel).start()
convert_many(['Diamond', 'Iron Ingot', 'Enchantment Table'],
             converter_factory=lambda l, cache: c)

print(c.is_cancelled())          # True
print(c.unresolved_templates)    # frozenset({'HistoryTable', ...})
```

### 出力ファイル命名

`_slug()` でファイル名を決定：
- 無効なファイル名文字（`\ / : * ? " < > |`）→ `_`
- スペース → `_`
- 絵文字/上位 Unicode → 削除
- 空タイトルフォールバック → `untitled`
- 名前の競合: 自動接尾辞 `-2`, `-3` など; 999 を超える競合は uuid プレフィックスを使用

### 入力ファイル形式（`-i`）

```
# コメント行（# プレフィックス）
Diamond
Iron Ingot
# 空行は自動スキップ
```

### 共有キャッシュ（永続化なし）

1 ページ `convert()` は `template_cache` の受け渡し भी 同プロセス共有をサポート：

```python
from minecraft_wiki_mdifier import convert

shared = {}
convert("Diamond", template_cache=shared)  # 24 テンプレート展開
convert("Iron Ingot", template_cache=shared)  # +17 新規、24 共有
```

**ディスクキャッシュとの差分**:
- `template_cache` パラメータ: プロセス内のみ、ディスク書き込みなし
- ディスクキャッシュ（`~/.cache/mdifier/`）: プロセス間、実行間
- `convert_many()` はディスクキャッシュを使用; 単一呼び出しの中間キャッシュは書き込みません

### キャッシュコマンド

| コマンド | 動作 | 用途 |
|---------|--------|------|
| `mdifier cache info` | 読み取り専用統計 | キャッシュ状態を表示 |
| `mdifier cache clear` | キャッシュファイル全体を削除 | Wiki 大規模更新、強制再構築 |
| `mdifier cache prune` | 期限切れ以外（7 日以内）を保持し、期限切れを削除 | routine maintenance |

`cache clear` はデフォルトで確認を求めます（`-y` でスキップ）。

## プロジェクト構造

```
src/minecraft_wiki_mdifier/
├── __init__.py           # convert/convert_detailed/convert_many/search をエクスポート
├── lib.py                # ライブラリモード API（convert_many を含む）
├── cli.py                # CLI エントリ（click、batch/cache サブコマンド付き）
├── wiki.py               # MediaWiki API 取得 + HTML フォールバック
├── parser.py             # Wikitext パーサー（テンプレート/リンク/見出し）
├── template_expander.py  # テンプレート展開: action=bucket または action=parse + 形式検出
├── formatters.py         # Minecraft カラーコード → 意味ラベル
├── converter.py          # Markdown 生成: ディスパッチレンダリング
├── cache.py              # テンプレート展開キャッシュの永続化
├── exceptions.py         # カスタム例外階層（BucketAPIError を含む）
├── _session.py          # HTTP Session ファクトリ（リトライ設定、User-Agent）
└── _validators.py       # 言語バリデータ（循環依存回避）
```

### データフロー

1. `WikiFetcher` → MediaWiki API が wikitext を取得
2. `WikiParser` → AST を解析、テンプレートを `templates` 辞書に抽出
3. `TemplateExpander` → Lua データクエリテンプレート（Trade uses など）の場合、`action=bucket` を 먼저試し、`action=parse` にフォールバック
4. `MarkdownConverter` → 適切なレンダラーにディスパッチ、最終的な Markdown を生成
5. 実行間: `get_or_load_persistent_cache()` がディスクキャッシュシングルトンを遅延ロード; バッチは終了時にのみ `save_cache()` を実行

## 開発

### 開発依存関係のインストール

```bash
pip install -e ".[dev]"
pre-commit install
```

### Ruff の実行

```bash
ruff check .
```

または pre-commit を使用（コミット時に自動実行）：
```bash
pre-commit run --all-files
```

### 手動テスト

```bash
mdifier convert "Diamond" -o diamond.md
mdifier cache info
mdifier cache clear -y
```

## ライセンス

MIT