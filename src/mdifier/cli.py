"""
命令行接口

用法:
    mdifier "页面标题"                    # 转换页面
    mdifier "页面标题" -o output.md        # 输出到文件
    mdifier "https://zh.minecraft.wiki/页面"  # URL方式
    mdifier search "关键词"                # 搜索页面
"""

import sys

import click

from mdifier import __version__
from mdifier.lib import convert, convert_many, search
from mdifier.wiki import LANG_CONFIG

LANGUAGES = list(LANG_CONFIG.keys())


@click.group()
@click.version_option(version=__version__, prog_name="mdifier")
def main():
    """
    Minecraft Wiki MDifier

    将Minecraft Wiki页面转换为AI助手易读的Markdown格式
    """
    pass


@main.command()
@click.argument("title_or_url", type=str)
@click.option(
    "-o", "--output",
    type=click.Path(),
    default=None,
    help="输出文件路径，默认为标准输出"
)
@click.option(
    "-l", "--lang",
    type=click.Choice(LANGUAGES, case_sensitive=False),
    default="zh",
    help="语言"
)
@click.option(
    "--include-templates",
    is_flag=True,
    default=False,
    help="在返回结果中包含模板数据"
)
def convert_cmd(
    title_or_url: str,
    output: str | None,
    lang: str,
    include_templates: bool
):
    """
    转换Wiki页面为Markdown

    示例:
        mdifier "铁锭"
        mdifier "铁锭" -o iron_ingot.md
        mdifier "https://zh.minecraft.wiki/铁锭"
    """
    try:
        markdown = convert(title_or_url, lang=lang, include_templates=include_templates)

        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(markdown)
            click.echo(f"已保存到: {output}")
        else:
            click.echo(markdown)

    except ValueError as e:
        click.echo(f"错误: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"未知错误: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("query", type=str)
@click.option(
    "-l", "--lang",
    type=click.Choice(LANGUAGES, case_sensitive=False),
    default="zh",
    help="语言"
)
@click.option(
    "-n", "--num",
    type=int,
    default=10,
    help="返回结果数量"
)
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

        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            desc = r.get("description", "")
            url = r.get("url", "")

            click.echo(f"{i}. {title}")
            if desc:
                click.echo(f"   {desc}")
            if url:
                click.echo(f"   {url}")
            click.echo()

    except Exception as e:
        click.echo(f"错误: {e}", err=True)
        sys.exit(1)


@main.command(name="batch")
@click.option("titles", "-t", "--title", multiple=True,
              help="页面标题（可多次使用）")
@click.option("-i", "--input-file", type=click.Path(exists=True), default=None,
              help="标题列表文件（每行一个；# 开头为注释）")
@click.option("--from-search", default=None, help="通过搜索获取标题")
@click.option("--search-limit", type=int, default=20,
              help="--from-search 时返回的最大结果数")
@click.option(
    "-l", "--lang",
    type=click.Choice(LANGUAGES, case_sensitive=False), default="zh"
)
@click.option("-o", "--output-dir", type=click.Path(file_okay=False), default=None,
              help="输出目录；为 None 则打印到 stdout")
@click.option("--workers", type=int, default=4, help="跨页并发抓取数")
@click.option("--no-progress", is_flag=True, default=False, help="禁用进度条")
def batch_cmd(
    titles, input_file, from_search, search_limit,
    lang, output_dir, workers, no_progress
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
            items.extend(
                r["title"] for r in search(from_search, lang=lang)[:search_limit]
            )
        if not items:
            click.echo("错误: 没有提供任何标题（用 -t / -i / --from-search）", err=True)
            sys.exit(2)

        # 去重保留顺序
        seen, deduped = set(), []
        for t in items:
            if t not in seen:
                seen.add(t)
                deduped.append(t)

        progress = _make_progress(len(deduped), enabled=not no_progress)
        result = convert_many(
            deduped, lang=lang, max_workers=workers, on_progress=progress
        )
        _emit_results(result, output_dir)

        if result.failed:
            click.echo(
                f"\n完成: {len(result.results)} 成功, {len(result.failed)} 失败",
                err=True,
            )
            for t, err in result.failed:
                click.echo(f"  - {t}: {err}", err=True)
            sys.exit(1)
        click.echo(f"完成: {len(result.results)} 成功", err=True)
    except Exception as e:
        click.echo(f"未知错误: {e}", err=True)
        sys.exit(2)


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
        last = [0]
        threshold = max(1, total // 20)

        def cb(done, total, title):
            if done == total or done - last[0] >= threshold:
                click.echo(f"\r进度: {done}/{total}", nl=False, err=True)
                last[0] = done

        return cb

    bar = tqdm(total=total, unit="page", dynamic_ncols=True)

    def cb(done, total, title):
        bar.update(1)
        bar.set_postfix_str(title[:30])

    return cb


def _emit_results(result, output_dir: str | None) -> None:
    """输出结果到 stdout 或文件目录"""
    if not output_dir:
        for i, r in enumerate(result.results):
            if i > 0:
                click.echo("\n---\n")
            click.echo(f"# {r.title}\n")
            click.echo(r.markdown)
        return

    from pathlib import Path
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    for r in result.results:
        path = _unique_path(out, _slug(r.title) + ".md", used_names)
        path.write_text(r.markdown, encoding="utf-8")
        used_names.add(path.name)


def _slug(title: str) -> str:
    """标题转文件名安全字符串"""
    import re
    s = re.sub(r'[\\/:*?"<>|]', "_", title)
    s = re.sub(r"\s+", "_", s.strip())
    return s or "untitled"


def _unique_path(out, name: str, used: set[str]):
    """生成唯一文件路径（冲突加 -2、-3 后缀）"""
    p = out / name
    if p.name not in used and not p.exists():
        return p
    stem, suffix = p.stem, p.suffix
    for i in range(2, 1000):
        cand = out / f"{stem}-{i}{suffix}"
        if cand.name not in used and not cand.exists():
            return cand
    import uuid
    return out / f"{stem}-{uuid.uuid4().hex[:6]}{suffix}"


if __name__ == "__main__":
    main()
