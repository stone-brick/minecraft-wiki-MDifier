<div align="center">

# ⚡ Minecraft Wiki MDifier

AI ツール向けに特別に設計：Minecraft Wiki をクリーンかつ構造化された Markdown 形式へ完璧に変換。

[![PyPI version](https://img.shields.io/pypi/v/minecraft-wiki-mdifier.svg)](https://pypi.org/project/minecraft-wiki-mdifier/)

**[中文](./README.md)** · **[English](./README-en.md)**

</div>

## 起源

AI 助手を使い始めると、もう手作業には戻れません——データパックの自作も然り。
Minecraft Wiki の取得時、プレー HTML はスタイルノイズだらけ、
プレー wikitext は汎用パーサーが処理できないテンプレート構文があります。

だったら自分でツールを作ろう。GitHub で検索しましたが、専念ツールは存在しませんでした。
@minecraft-wiki-MCP を見つけ、もっと良いパースが必要だと気づき（すでにリライト済み）、
需要があると気づいて、急いで作りました。

開発中は何度も壁にぶつかり、より良い方法を模索し、
現在の `action=bucket` + `action=expandtemplates` + `action=parse` 三層フォールバック架构に辿り着きました。

## 問題と解決

Minecraft Wiki 処理には二大类の難題があります：

### Markdown への変換について

**1. テンプレート取得が遅い**
Wiki ページのテンプレート参照を展開するには多数のリクエストが必要で、時間が膨大にかかります。

**2. テンプレートが展開できない**
`{{Crafting}}`、`{{Trade}}` などのテンプレートは Lua モジュールとデータベースに依存しており、純パーサーでは描画結果を取得できません。

**3. クリーニングが不十分**
描画後の HTML には無用な class、style、data 属性や余分なタグが含まれています。

**4. Wikitext 構文が曖昧**
Bold/Italic タグのネスト、`{{end-bold}}` などの MediaWiki 固有構文は、汎用パーサーが誤判断しやすいです。

### AI 助手での使用について

**5. HTML がコンテキストを占有し、セマンティクスを乱す**
プレー HTML には無関係なタグや追加情報がたくさんあり、トークンを浪費し LLM の理解に影響します。

**6. Wikitext テンプレートの情報が省略される**
Wikitext のテンプレートはただのプレースホルダーで、原文にはテンプレート展開後の実際の 내용이含まれておらず、AI は構造化データをここから學べません。

mdifier の解決策：
- `action=bucket` API で構造化データ（Lua データ）を取得
- `action=expandtemplates` API でテンプレートを展開
- HTML の冗長属性をクリーニングし、セマンティック構造を保持
- テンプレートの展開結果をキャッシュして API 呼び出しを削減

**性能比較**（Diamond、Iron Ingot、Gold Ingot の変換）：

| アプローチ | 耗时 | 高速化 |
| --------- | ------ | --------- |
| キャッシュなし、直列（ベースライン） | 51.37s | 1.0x |
| キャッシュなし、並列 | 22.00s | 2.3x |
| キャッシュあり（コールド） | 19.02s | 2.7x |
| キャッシュあり（ホット） | 0.20s | **251.9x** |

## インストール

**Python >= 3.11** が必要です。

```bash
# PyPI からインストール（推奨）
pip install minecraft-wiki-mdifier

# ローカル開発用
pip install -e .
```

確認：

```bash
mdifier --version
# または: python -m minecraft_wiki_mdifier.cli --version
```

## クイックスタート

```bash
# ページを変換（中国語 wiki デフォルト）
mdifier convert "Iron Ingot"

# ファイルに保存
mdifier convert "Iron Ingot" -o iron.md

# 中国語 wiki
mdifier convert "铁锭" --lang zh -o iron.md

# URL から言語を自動検出
mdifier convert "https://minecraft.wiki/wiki/Iron_Ingot"
mdifier convert "https://ja.minecraft.wiki/wiki/鉄インゴット"

# 検索
mdifier search "diamond"
mdifier search "ダイヤモンド" --lang ja

# バッチ変換
mdifier batch -t Diamond -t Iron_Ingot -o ./out
mdifier batch -i pages.txt -o ./out --workers 8
mdifier batch -t Diamond --no-markers  # テンプレートマーカー無効化

# キャッシュ管理
mdifier cache info
mdifier cache clear -y   # キャッシュをクリア
mdifier cache prune       # 期限切れエントリを削除
```

## ユースケース

**MCP / Skills / Agent 構築**
AI 助手に Minecraft Wiki データを提供し、ゲームの質問に答えられる Agent を構築します。

```python
from minecraft_wiki_mdifier import convert_many

pages = ["Diamond", "Iron Ingot", "Gold Ingot", "Emerald", "Lapis Lazuli"]
result = convert_many(pages)
# クリーンな Markdown 出力、直接コンテキスト注入に使用可能
```

**RAG ナレッジベース**
Wiki コンテンツをベクトル化し、ローカルナレッジベースを構築：

```python
result = convert_detailed("Iron Ingot")
print(result.markdown)  # クリーンなテキスト、チャンク化和ベクトル化に直接使用可能
```

**MOD 開発データクエリ**
村人の交易やモブのドロップなどの構造化データを取得：

```python
from minecraft_wiki_mdifier import convert_detailed

result = convert_detailed("Armorer")
print(result.templates["trade"][0]["wanted_item"])  # 防具鍛冶の欲しいアイテム
```

## CLI リファレンス

### convert

```bash
mdifier convert "TITLE_OR_URL" [-o OUTPUT] [--lang {zh|en|ja}] [--detail]
```

| オプション | 説明 |
|-----------|------|
| `-o, --output` | 出力ファイルパス |
| `-l, --lang` | 言語（デフォルト zh） |
| `--detail` | 完全な JSON 出力（title, markdown, source, templates） |

### search

```bash
mdifier search "QUERY" [-l {zh|en|ja}] [-n NUM]
```

| オプション | 説明 |
|-----------|------|
| `-n NUM` | 結果数（デフォルト 10） |

### batch

```bash
mdifier batch [-t TITLE] [-i FILE] [--from-search QUERY] [-o DIR] [--workers N] [--no-progress] [--marker-format FORMAT]
```

| オプション | 説明 |
|-----------|------|
| `-t, --title` | ページタイトル（複数可） |
| `-i, --input-file` | タイトルリストファイル（1 行 1 タイトル、`#` はコメント） |
| `--from-search` | 検索からタイトルを取得 |
| `--search-limit` | `--from-search` の最大結果数 |
| `-o, --output-dir` | 出力ディレクトリ；None の場合は stdout に出力 |
| `--workers` | 並発ページフェッチ数（デフォルト 4） |
| `--no-progress` | 進捗バーを無効化 |
| `--marker-format` | カスタムマーカー形式 `open/close`（`{name}` = テンプレートクラス名） |
| `--no-markers` | テンプレートマーカー（`:::name`）を無効化 |

### cache

```bash
mdifier cache info|clear|prune
```

- `info` — 統計（パス、サイズ、エントリ数、期限切れ数、タイムスタンプ）
- `clear` — キャッシュ全体をクリア（`-y` で確認をスキップ）
- `prune` — 期限切れエントリのみ削除

## Python API

```python
from minecraft_wiki_mdifier import convert, convert_detailed, convert_many, search

# 简单変換
md = convert("Iron Ingot")

# 詳細モード
result = convert_detailed("Iron Ingot")
print(result.title)      # ページタイトル
print(result.source)    # "api" または "html"
print(result.templates) # テンプレートデータ dict

# バッチ変換
result = convert_many(["Diamond", "Iron Ingot", "Enchantment Table"], max_workers=4)
for r in result.results:
    print(f"=== {r.title} ===")
if result.failed:
    print(f"失敗: {result.failed}")
if result.unresolved:
    print(f"未展開テンプレート: {result.unresolved}")

# 検索
results = search("diamond", lang="en")
for r in results[:5]:
    print(f"{r['title']}: {r['description']}")
```

### URL 自動検出

| 入力 | 検出結果 |
|------|----------|
| `https://minecraft.wiki/wiki/Iron_Ingot` | en |
| `https://zh.minecraft.wiki/wiki/铁锭` | zh |
| `https://ja.minecraft.wiki/wiki/鉄インゴット` | ja |
| プレーンタイトル | `lang` パラメータを使用（デフォルト zh） |

### 言語横断バッチ

```python
items = [
    "Diamond",                                     # en
    "https://zh.minecraft.wiki/wiki/钻石",          # zh（URL 検出）
    "Iron Ingot",                                   # デフォルト lang を使用
]
result = convert_many(items, lang="en")
```

## 上級用法

### カスタムテンプレートマーカー

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

### バッチキャンセル

```python
import threading
from minecraft_wiki_mdifier.converter import MarkdownConverter

c = MarkdownConverter(lang='en')
threading.Timer(0.5, c.cancel).start()  # 0.5 秒後にキャンセル

convert_many(['Diamond', 'Iron Ingot', 'Enchantment Table'],
             converter_factory=lambda l, cache: c)

print(c.is_cancelled())       # True
print(c.unresolved_templates) # frozenset({'HistoryTable', ...})
```

### 呼び出し間共有キャッシュ

```python
shared = {}
convert("Diamond", template_cache=shared)   # 24 テンプレート展開
convert("Iron Ingot", template_cache=shared) # +17 新規、24共有
```

注意：`template_cache` はプロセス内のみ、ディスク書き込みなし；ディスクキャッシュ（`~/.cache/mdifier/`）はプロセス間共有。

### カラーコード

```python
from minecraft_wiki_mdifier.formatters import MinecraftColorFormatter

f = MinecraftColorFormatter()
f.clean("&e黄色&rリセット")  # '[yellow]黄色[reset]リセット'
```

## テンプレート処理

テンプレートは `:::{name}` マーカーでラップされ、内容タイプが描画方法を決定：

| テンプレート | 出力 |
|------------|------|
| `Infobox` | 2列 Markdown テーブル |
| `Crafting` | 3列: 材料 / レシピ / 説明 |
| `LootChest` | 6列: アイテム / ソース / 量 / 確率など |
| `mcui`（作業台/炉/織機/鍛造台） | 3x3 グリッドテキスト + アイテム説明 |
| `Hatnote`, `Quote` | markdownify で変換 |
| 未認識 | 汎用 markdownify 変換 |
| 展開失敗 | フォールバック `[template: k=v]`、`class="error"` でマーク |

一部のテンプレート（Trade uses、Crafting usage など）は Lua Bucket データベースに依存し、`action=bucket` API でクエリ。

## キャッシュ

- **場所**: `~/.cache/mdifier/templates.json`
- **TTL**: 7 日間
- **共有**: プロセス間、実行間
- **高速化**: 初回約 6 秒、2 回目約 1 秒（**5.4x**）

Python API：

```python
from minecraft_wiki_mdifier.cache import cache_info, clear_cache

info = cache_info()
if info["size_mb"] > 100:
    clear_cache()
```

## エラーハンドリング

### Python 例外

```python
from minecraft_wiki_mdifier import convert, InvalidInputError

try:
    md = convert("nonexistent_page")
except InvalidInputError as e:  # ValueError を継承
    print(f"失敗: {e}")
```

**例外階層**：

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

### CLI 終了コード

| コード | 名前 | 意味 |
|------|------|------|
| 0 | Success | 正常終了 |
| 64 | `EX_USAGE` | コマンドエラー |
| 65 | `EX_DATAERR` | データエラー（ページなし、バッチ一部失敗） |
| 70 | `EX_SOFTWARE` | ソフトウェアエラー |
| 74 | `EX_IOERR` | I/O エラー |
| 75 | `EX_TEMPFAIL` | ネットワーク一時エラー |
| 77 | `EX_NOPERM` | 権限エラー |

## 多言語対応

組み込みの `zh`（zh.minecraft.wiki）、`en`（minecraft.wiki）、`ja`（ja.minecraft.wiki）。

**注意**: ja wiki の Bucket i18n フィールドには中国語のデータが含まれている。プログラムはデフォルトで翻訳せず、英語原文を出力。

## プロジェクト構造

```
src/minecraft_wiki_mdifier/
├── __init__.py           # 公開 API エクスポート
├── lib.py                # convert / convert_many / search
├── cli.py                # CLI エントリ（click）
├── wiki.py               # MediaWiki API 取得 + HTML フォールバック
├── parser.py             # Wikitext パーサー
├── template_expander.py  # テンプレート展開（bucket/expandtemplates）
├── formatters.py         # Minecraft カラーコードフォーマッタ
├── converter.py          # Markdown 生成
├── cache.py              # テンプレートキャッシュ永続化
├── exceptions.py         # 例外階層
├── _session.py           # HTTP Session ファクトリ
└── _validators.py        # 言語バリデータ
```

**データフロー**：

1. `WikiFetcher` → MediaWiki API が wikitext を取得
2. `WikiParser` → AST を解析、テンプレートを抽出
3. `TemplateExpander` → `action=bucket` を優先、`action=expandtemplates` にフォールバック
4. `MarkdownConverter` → レンダラーにディスパッチ、Markdown を生成

## 貢献

あらゆる形態の貢献を歓迎します：

- 🐛 バグを発見しましたか？[Issue を開く](https://github.com/stone-brick/minecraft-wiki-MDifier/issues)
- 💡 アイデアはありますか？[Discussion](https://github.com/stone-brick/minecraft-wiki-MDifier/discussions) で話す
- 📖 ドキュメントを改善できますか？PR を送ってください

### 開発環境

```bash
git clone https://github.com/stone-brick/minecraft-wiki-MDifier
cd minecraft-wiki-MDifier
pip install -e ".[dev]"
pytest
```

## ライセンス

MIT
