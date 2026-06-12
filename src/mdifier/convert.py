"""
Minecraft Wiki 页面转换为 Markdown

调用方式:
    python convert.py --title "钻石" --output result.md --lang zh
"""
import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / 'src'))

from mdifier.lib import convert


def main():
    parser = argparse.ArgumentParser(description='转换Minecraft Wiki页面')
    parser.add_argument('--title', required=True, help='页面标题')
    parser.add_argument('--output', default=None, help='输出文件路径')
    parser.add_argument('--lang', default='zh', choices=['zh', 'en'], help='语言')
    args = parser.parse_args()

    try:
        result = convert(args.title, lang=args.lang)

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(result)
            print(f"已保存到: {args.output}")
        else:
            print(result)

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()