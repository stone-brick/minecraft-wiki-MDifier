"""
命令行接口

用法:
    mdifier convert "页面标题"            # 转换页面
    mdifier convert "页面标题" -o x.md    # 输出到文件
    mdifier convert "https://zh.minecraft.wiki/页面"  # URL方式
    mdifier search "关键词"              # 搜索页面
"""

import re
import sys
from pathlib import Path

import click

from minecraft_wiki_mdifier.converter import MarkdownConverter
from minecraft_wiki_mdifier.exceptions import FetchError, InvalidInputError, PageNotFoundError
from minecraft_wiki_mdifier.lib import convert, convert_detailed, convert_many, search
from minecraft_wiki_mdifier.wiki import LANG_CONFIG

from . import __version__

# BSD sysexits.h 退出码（Python 3.13+ 统一支持）
EXIT_OK = 0
EXIT_USAGE = 64  # 命令行参数错
EXIT_DATAERR = 65  # 数据错
EXIT_SOFTWARE = 70  # 内部软件错
EXIT_IOERR = 74  # 本地 I/O 错
EXIT_TEMPFAIL = 75  # 网络临时失败
EXIT_NOPERM = 77  # 权限错
EXIT_CONFIG = 78  # 配置错

LANGUAGES = list(LANG_CONFIG.keys())


@click.group()
@click.version_option(version=__version__, prog_name="mdifier")
def main():
    """
    Minecraft Wiki MDifier

    将Minecraft Wiki页面转换为AI助手易读的Markdown格式

    子命令：convert / search / batch / cache
    """
    pass


@main.command()
@click.argument("title_or_url", type=str, metavar="TITLE_OR_URL")
@click.option(
    "-o", "--output", type=click.Path(), default=None, help="输出文件路径，默认为标准输出"
)
@click.option(
    "-l",
    "--lang",
    type=click.Choice(LANGUAGES, case_sensitive=False),
    default="zh",
    help="语言（默认 zh，支持自动 URL 识别）",
)
@click.option(
    "--detail",
    is_flag=True,
    help="输出完整 JSON（包含 title、markdown、source、templates）",
)
def convert_cmd(
    title_or_url: str,
    output: str | None,
    lang: str,
    detail: bool,
):
    """
    转换Wiki页面为Markdown

    支持纯标题或自动识别 URL（zh.minecraft.wiki / minecraft.wiki / en.minecraft.wiki）

    示例:
        mdifier convert "铁锭"
        mdifier convert "铁锭" -o iron_ingot.md
        mdifier convert "铁锭" --detail     # 完整 JSON 输出
        mdifier convert "https://zh.minecraft.wiki/铁锭"
    """
    try:
        if detail:
            import json

            result = convert_detailed(title_or_url, lang=lang)
            content = json.dumps(
                {
                    "title": result.title,
                    "markdown": result.markdown,
                    "source": result.source,
                    "templates": result.templates,
                },
                ensure_ascii=False,
                indent=2,
            )
        else:
            content = convert(title_or_url, lang=lang)

        if output:
            try:
                # 解析为绝对路径：避免 Git Bash 的 MSYS 路径翻译
                # 相对路径基于 cwd；绝对路径不变
                out_path = Path(output).resolve()
                if out_path.parent and not out_path.parent.exists():
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(content, encoding="utf-8")
                click.echo(f"已保存到: {out_path}")
            except FileNotFoundError as e:
                click.secho(f"错误: 路径无效 ({output}): {e}", fg="red", err=True)
                sys.exit(EXIT_IOERR)
            except PermissionError as e:
                click.secho(f"错误: 无写权限 ({output}): {e}", fg="red", err=True)
                sys.exit(EXIT_NOPERM)
            except OSError as e:
                click.secho(f"错误: 写入文件失败 ({output}): {e}", fg="red", err=True)
                sys.exit(EXIT_IOERR)
        else:
            click.echo(content)

    except InvalidInputError as e:
        click.secho(f"错误: {e}", fg="red", err=True)
        sys.exit(EXIT_USAGE)
    except PageNotFoundError as e:
        click.secho(f"页面未找到: {e}", fg="red", err=True)
        sys.exit(EXIT_DATAERR)
    except FetchError as e:
        click.secho(f"网络错误: {e}", fg="red", err=True)
        sys.exit(EXIT_TEMPFAIL)
    except Exception as e:
        click.secho(f"未知错误: {type(e).__name__}: {e}", fg="red", err=True)
        sys.exit(EXIT_SOFTWARE)


@main.command()
@click.argument("query", type=str)
@click.option(
    "-l",
    "--lang",
    type=click.Choice(LANGUAGES, case_sensitive=False),
    default="zh",
    help="语言（默认 zh）",
)
@click.option("-n", "--num", type=int, default=10, help="返回结果数量（默认 10）")
def search_cmd(query: str, lang: str, num: int):
    """
    搜索Wiki页面

    示例:
        mdifier search "钻石"
    """
    try:
        results = search(query, lang=lang)[:num]

        if not results:
            click.echo("未找到结果")
            return

        for i, result in enumerate(results, 1):
            title = result.get("title", "")
            if not title:
                continue
            desc = result.get("description", "")
            url = result.get("url", "")

            click.echo(f"{i}. {title}")
            if desc:
                click.echo(f"   {desc}")
            if url:
                click.echo(f"   {url}")
            if i < len(results):
                click.echo()

    except Exception as e:
        click.secho(f"错误: {e}", fg="red", err=True)
        sys.exit(EXIT_SOFTWARE)


@main.command(name="batch")
@click.option("titles", "-t", "--title", multiple=True, help="页面标题（可多次使用）")
@click.option(
    "-i",
    "--input-file",
    type=click.Path(exists=True),
    default=None,
    help="标题列表文件（每行一个；# 开头为注释）",
)
@click.option("--from-search", default=None, help="通过搜索获取标题")
@click.option("--search-limit", type=int, default=20, help="--from-search 时返回的最大结果数")
@click.option(
    "-l",
    "--lang",
    type=click.Choice(LANGUAGES, case_sensitive=False),
    default="zh",
    help="默认语言（默认 zh）",
)
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(file_okay=False),
    default=None,
    help="输出目录；为 None 则打印到 stdout",
)
@click.option("--workers", type=int, default=4, help="跨页并发抓取数")
@click.option("--no-progress", is_flag=True, default=False, help="禁用进度条")
@click.option(
    "--marker-format", default=None, help="自定义模板标记，格式 'open/close'，如 ':::{name}:::/:::'"
)
def batch_cmd(
    titles,
    input_file,
    from_search,
    search_limit,
    lang,
    output_dir,
    workers,
    no_progress,
    marker_format,
):
    """
    批量转换 Wiki 页面

    示例:
        mdifier batch -t 钻石 -t 铁锭 -o ./out
        mdifier batch -i pages.txt -o ./out --workers 8
        mdifier batch --from-search "红石" --search-limit 30 -o ./out
    """
    try:
        items: list[str] = list(titles)
        if input_file:
            items.extend(_read_titles_file(input_file))
        if from_search:
            items.extend(r["title"] for r in search(from_search, lang=lang)[:search_limit])
        if not items:
            click.secho("错误: 没有提供任何标题（用 -t / -i / --from-search）", fg="red", err=True)
            sys.exit(EXIT_USAGE)

        # 去重保留顺序
        seen, deduped = set(), []
        for title in items:
            if title not in seen:
                seen.add(title)
                deduped.append(title)

        progress = _make_progress(len(deduped), enabled=not no_progress)
        # 解析 --marker-format 为 converter_factory
        converter_factory = None
        if marker_format:
            try:
                open_, close_ = marker_format.split("/", 1)
            except ValueError:
                click.secho(
                    "错误: --marker-format 格式为 'open/close'，必须包含 '/'", fg="red", err=True
                )
                sys.exit(EXIT_USAGE)

            def _make_converter(item_lang: str, cache: dict | None):
                c = MarkdownConverter(lang=item_lang, template_cache=cache)
                c.template_marker_open = open_
                c.template_marker_close = close_
                return c

            converter_factory = _make_converter
        result = convert_many(
            deduped,
            lang=lang,
            max_workers=workers,
            on_progress=progress,
            converter_factory=converter_factory,
        )
        _emit_results(result, output_dir)

        # 报告未展开的模板
        if result.unresolved:
            click.secho(
                f"\n⚠️  警告：{len(result.unresolved)} 个模板未展开（驼峰映射缺失或模板不存在）：",
                fg="yellow",
                err=True,
            )
            for name in result.unresolved:
                click.secho(f"  - {name}", fg="yellow", err=True)
            click.secho("建议添加到 MarkdownConverter.CAMEL_CASE_TEMPLATES", fg="yellow", err=True)

        if result.failed:
            click.echo(
                f"\n完成: {len(result.results)} 成功, {len(result.failed)} 失败",
                err=True,
            )
            for t, err in result.failed:
                click.echo(f"  - {t}: {err}", err=True)
            sys.exit(EXIT_DATAERR)
        click.echo(f"完成: {len(result.results)} 成功", err=True)
    except Exception as e:
        click.secho(f"未知错误: {e}", fg="red", err=True)
        sys.exit(EXIT_SOFTWARE)


@main.group()
def cache():
    """管理模板展开缓存"""


@cache.command(name="info")
def cache_info_cmd():
    """显示缓存统计信息（路径、大小、条目、时间戳）"""
    from minecraft_wiki_mdifier.cache import cache_info

    info = cache_info()
    click.echo(f"路径:    {info['path']}")
    click.echo(f"存在:    {info['exists']}")
    if info["exists"]:
        click.echo(f"大小:    {info['size_bytes']:,} 字节 ({info['size_mb']} MB)")
        click.echo(f"总条目:  {info['entries']}")
        click.echo(f"  未过期: {info['fresh_entries']}")
        click.echo(f"  已过期: {info['expired_entries']}")
        if info["oldest_ts"]:
            click.echo(f"最早:    {info['oldest_ts']}")
            click.echo(f"最新:    {info['newest_ts']}")


@cache.command(name="clear")
@click.option("-y", "--yes", is_flag=True, help="跳过确认提示")
def cache_clear_cmd(yes):
    """清空整个缓存文件（强制下次重新请求）"""
    from minecraft_wiki_mdifier.cache import cache_info, clear_cache

    info = cache_info()
    if not info["exists"]:
        click.echo("缓存不存在，无需清理", err=True)
        return

    if not yes:
        click.confirm(
            f"确定删除 {info['size_mb']} MB、{info['entries']} 条目的缓存？",
            abort=True,
        )
    if clear_cache():
        click.secho(
            f"✓ 已清空缓存：{info['size_mb']} MB、{info['entries']} 条目", fg="green", err=True
        )
    else:
        click.echo("缓存不存在", err=True)


@cache.command(name="prune")
def cache_prune_cmd():
    """清理已过期条目（保留 < 7 天的 fresh 条目）"""
    from minecraft_wiki_mdifier.cache import CACHE_FILE, CACHE_TTL, cache_info

    info = cache_info()
    if not info["exists"]:
        click.echo("缓存不存在", err=True)
        return
    if info["expired_entries"] == 0:
        click.echo(f"无过期条目（共 {info['entries']} 条目，全部未过期）", err=True)
        return
    # 加载 → 过滤 → 写回
    import json
    import time

    cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    now = time.time()
    pruned = {k: v for k, v in cache.items() if now - v.get("ts", 0) < CACHE_TTL}
    removed = len(cache) - len(pruned)
    CACHE_FILE.write_text(
        json.dumps(pruned, ensure_ascii=False),
        encoding="utf-8",
    )
    click.secho(f"✓ 清理完成：移除 {removed} 条过期，保留 {len(pruned)} 条", fg="green", err=True)


def _read_titles_file(path: str) -> list[str]:
    """从文件读取标题列表"""
    titles: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            titles.append(line)
    return titles


def _make_progress(total: int, enabled: bool):
    """构造进度回调（tqdm 优先，缺失降级为 stderr 文本）"""
    if not enabled:
        return lambda done, total, title: None

    try:
        from tqdm import tqdm
    except ImportError:
        last_emitted = 0
        threshold = max(1, total // 20)

        def progress_callback(done, total, title):
            nonlocal last_emitted
            if done == total or done - last_emitted >= threshold:
                click.echo(f"\r进度: {done}/{total}", nl=False, err=True)
                last_emitted = done

        return progress_callback

    bar = tqdm(total=total, unit="page", dynamic_ncols=True)

    def progress_callback(done, total, title):
        bar.update(1)
        bar.set_postfix_str(title[:30])

    return progress_callback


def _emit_results(result, output_dir: str | None) -> None:
    """输出结果到 stdout 或文件目录"""
    if not output_dir:
        for i, r in enumerate(result.results):
            if i > 0:
                click.echo("\n---\n")
            click.echo(f"# {r.title}\n")
            click.echo(r.markdown)
        return

    # 解析为绝对路径：避免 Git Bash 的 MSYS 路径翻译
    out_dir = Path(output_dir).resolve()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        click.secho(f"错误: 无写权限创建目录 ({out_dir}): {e}", fg="red", err=True)
        return
    except OSError as e:
        click.secho(f"错误: 创建目录失败 ({out_dir}): {e}", fg="red", err=True)
        return
    used_names: set[str] = set()
    for r in result.results:
        path = _unique_path(out_dir, _slug(r.title) + ".md", used_names)
        try:
            path.write_text(r.markdown, encoding="utf-8")
        except (FileNotFoundError, PermissionError, OSError) as e:
            click.secho(f"警告: 写入失败 ({path}): {e}", fg="yellow", err=True)
            continue
        used_names.add(path.name)


def _slug(title: str) -> str:
    """标题转文件名安全字符串"""
    s = re.sub(r'[\\/:*?"<>|]', "_", title)
    s = re.sub(r"\s+", "_", s.strip())
    # 移除非BMP字符（emoji等在U+10000以上平面，不含CJK汉字）
    s = "".join(ch for ch in s if ord(ch) <= 0xFFFF)
    return s or "untitled"


def _unique_path(out_dir, name: str, used: set[str]):
    """生成唯一文件路径（冲突加 -2、-3 后缀）"""
    p = out_dir / name
    if p.name not in used and not p.exists():
        return p
    stem, suffix = p.stem, p.suffix
    for i in range(2, 1000):
        cand = out_dir / f"{stem}-{i}{suffix}"
        if cand.name not in used and not cand.exists():
            return cand
    import uuid

    return out_dir / f"{stem}-{uuid.uuid4().hex[:6]}{suffix}"


if __name__ == "__main__":
    main()
