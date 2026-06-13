"""
搜索 Minecraft Wiki 页面

调用方式:
    python search.py "钻石" --num 10 --lang zh
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径（允许在非安装环境下直接运行脚本）
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "src"))

from mdifier.lib import search


def main():
    parser = argparse.ArgumentParser(description="搜索Minecraft Wiki页面")
    parser.add_argument("query", help="搜索关键词")
    parser.add_argument("--num", type=int, default=10, help="返回结果数量")
    parser.add_argument("--lang", default="zh", choices=["zh", "en"], help="语言")

    args = parser.parse_args()

    try:
        results = search(args.query, lang=args.lang)[: args.num]

        if not results:
            print("未找到结果")
            return

        for i, r in enumerate(results, 1):
            print(f"{i}. {r.get('title', '')}")
            if r.get("description"):
                print(f"   {r['description']}")
            if r.get("url"):
                print(f"   {r['url']}")
            print()

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
