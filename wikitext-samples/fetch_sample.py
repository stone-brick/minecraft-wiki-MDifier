"""
获取页面 wikitext 样本的脚本

用法:
    python wikitext-samples/fetch_sample.py <页面标题> [-l <语言>]
    python wikitext-samples/fetch_sample.py 苹果
    python wikitext-samples/fetch_sample.py Apple -l en

输出:
    wikitext-samples/<lang>_<title>.txt
"""

import argparse
import sys
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from minecraft_wiki_mdifier.wiki import WikiFetcher


def fetch_and_save(title: str, lang: str = "zh") -> Path:
    """获取页面并保存为样本文件"""
    fetcher = WikiFetcher(lang=lang)
    page = fetcher.fetch_via_api(title)

    # 创建样本目录
    samples_dir = Path(__file__).parent
    samples_dir.mkdir(exist_ok=True)

    # 生成文件名：lang_title.txt
    safe_title = title.replace("/", "_").replace("\\", "_")
    filename = f"{lang}_{safe_title}.txt"
    output_path = samples_dir / filename

    output_path.write_text(page.content, encoding="utf-8")
    print(f"已保存: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="获取 Wiki 页面 wikitext 样本")
    parser.add_argument("title", help="页面标题")
    parser.add_argument(
        "-l", "--lang", default="zh", choices=["zh", "en", "ja"], help="语言 (默认: zh)"
    )
    args = parser.parse_args()

    fetch_and_save(args.title, args.lang)


if __name__ == "__main__":
    main()
