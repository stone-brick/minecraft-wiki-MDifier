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
from mdifier.lib import convert, search
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


if __name__ == "__main__":
    main()
