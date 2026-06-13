"""测试 cache 模块"""

import json
import time


class TestCache:
    def test_load_cache_file_not_exists(self, cache_dir):
        """文件不存在返回空 dict"""
        from mdifier.cache import load_cache

        assert load_cache() == {}

    def test_save_then_load(self, cache_dir):
        """保存后能加载回"""
        from mdifier.cache import load_cache, save_cache

        data = {
            "Hatnote|x": {
                "name": "hatnote",
                "class": "hatnote",
                "text": "test",
                "html": "<div>x</div>",
                "format": "text",
                "table": None,
            }
        }
        save_cache(data)
        loaded = load_cache()
        assert "Hatnote|x" in loaded
        assert loaded["Hatnote|x"]["text"] == "test"

    def test_save_adds_timestamp(self, cache_dir):
        """save_cache 自动加 _ts"""
        from mdifier.cache import load_cache, save_cache

        save_cache({"k": {"text": "x"}})
        loaded = load_cache()
        assert "ts" in loaded["k"]
        assert loaded["k"]["ts"] > 0

    def test_expired_entries_filtered(self, cache_dir):
        """过期条目（> 7 天）被过滤"""
        from mdifier.cache import CACHE_TTL, load_cache

        # 构造一条 8 天前的缓存
        expired_ts = time.time() - CACHE_TTL - 86400  # 8 天前
        with open(cache_dir / "templates.json", "w", encoding="utf-8") as f:
            json.dump({"k": {"text": "x", "_ts": expired_ts}}, f)
        loaded = load_cache()
        assert "k" not in loaded

    def test_corrupted_json_returns_empty(self, cache_dir):
        """损坏的 JSON 返回空 dict"""
        with open(cache_dir / "templates.json", "w", encoding="utf-8") as f:
            f.write("{ invalid json")
        from mdifier.cache import load_cache

        assert load_cache() == {}

    def test_clear_cache_existing(self, cache_dir):
        """clear_cache 删除存在的文件"""
        from mdifier.cache import clear_cache

        (cache_dir / "templates.json").write_text("{}", encoding="utf-8")
        assert clear_cache() is True
        assert not (cache_dir / "templates.json").exists()

    def test_clear_cache_missing(self, cache_dir):
        """clear_cache 对不存在的文件返回 False"""
        from mdifier.cache import clear_cache

        assert clear_cache() is False

    def test_cache_info_existing(self, cache_dir):
        """cache_info 9 字段"""
        from mdifier.cache import cache_info, save_cache

        save_cache({"k1": {"text": "x"}, "k2": {"text": "y"}})
        info = cache_info()
        assert info["exists"] is True
        assert info["entries"] == 2
        assert info["fresh_entries"] == 2
        assert info["expired_entries"] == 0
        assert info["size_bytes"] >= 0  # 文件可能极小
        assert info["size_mb"] >= 0.0
        assert info["oldest_ts"] is not None
        assert info["newest_ts"] is not None

    def test_cache_info_missing(self, cache_dir):
        """cache_info 对不存在的文件返回 exists=False"""
        from mdifier.cache import cache_info

        info = cache_info()
        assert info["exists"] is False
        assert info["entries"] == 0
        assert info["size_bytes"] == 0
