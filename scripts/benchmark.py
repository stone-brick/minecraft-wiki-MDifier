#!/usr/bin/env python3
"""
性能基准测试：测量不同缓存策略下的转换性能。

页面: ['工作台', '苦力怕', '苹果', '铁锭', 'Minecraft']
场景:
  1. 无缓存串行 - convert() 单线程，无缓存
  2. 无缓存并发 - convert_many() 多线程，无缓存
  3. 有缓存（冷）- convert_many()，磁盘持久缓存首次加载
  4. 有缓存（热）- convert_many()，缓存已在内存
"""

import time

from minecraft_wiki_mdifier import convert, convert_many
from minecraft_wiki_mdifier.cache import clear_cache, reset_persistent_cache

PAGES = ["工作台", "苦力怕", "苹果", "铁锭", "Minecraft"]


def run_benchmark() -> dict[str, float]:
    """运行四项性能测试，返回 {场景: 耗时秒}"""
    results = {}

    # ── 1. 无缓存串行 ──────────────────────────────────────────
    # 每次 convert() 用空 cache，确保无共享
    reset_persistent_cache()  # 重置模块单例
    clear_cache()  # 清空磁盘

    t0 = time.perf_counter()
    for page in PAGES:
        convert(page, lang="zh", template_cache={})
    results["无缓存串行"] = time.perf_counter() - t0

    # ── 2. 无缓存并发 ──────────────────────────────────────────
    # convert_many 内部模板展开有并发，但无持久缓存
    clear_cache()
    reset_persistent_cache()

    t0 = time.perf_counter()
    convert_many(PAGES, lang="zh", max_workers=4, template_cache={})
    results["无缓存并发"] = time.perf_counter() - t0

    # ── 3. 有缓存（冷）─────────────────────────────────────────
    # 清空磁盘，模拟冷启动：首次加载持久缓存
    clear_cache()
    reset_persistent_cache()

    t0 = time.perf_counter()
    convert_many(PAGES, lang="zh", max_workers=4, template_cache=None)
    results["有缓存（冷）"] = time.perf_counter() - t0

    # ── 4. 有缓存（热）─────────────────────────────────────────
    # 缓存已在内存，再次运行（不清空）
    t0 = time.perf_counter()
    convert_many(PAGES, lang="zh", max_workers=4, template_cache=None)
    results["有缓存（热）"] = time.perf_counter() - t0

    return results


def format_results(results: dict[str, float]) -> str:
    """格式化为 Markdown 表格"""
    baseline = results["无缓存串行"]
    rows = []
    for name, elapsed in results.items():
        speedup = baseline / elapsed if elapsed > 0 else float("inf")
        if name == "有缓存（热）" and elapsed < 1:
            rows.append(f"| {name} | {elapsed:.2f}s | **{speedup:.1f}x** |")
        else:
            rows.append(f"| {name} | {elapsed:.2f}s | {speedup:.1f}x |")

    header = "| 方案 | 耗时 | 加速比 |\n| --- | --- | --- |"
    return header + "\n" + "\n".join(rows)


if __name__ == "__main__":
    print("=" * 60)
    print("性能基准测试")
    print(f"页面: {PAGES}")
    print("=" * 60)
    print()

    results = run_benchmark()

    print("结果:")
    print(format_results(results))
    print()

    # 详细信息
    baseline = results["无缓存串行"]
    print("详细数据:")
    for name, elapsed in results.items():
        print(f"  {name}: {elapsed:.2f}s (加速比 {baseline / elapsed:.1f}x)")
