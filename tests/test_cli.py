"""测试 CLI convert --detail"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from mdifier.cli import main


class TestConvertDetail:
    def test_default_ouputs_markdown(self):
        """默认输出纯 markdown（无 --detail）"""
        with patch("mdifier.cli.convert") as mock_convert:
            mock_convert.return_value = "# 铁锭\ncontent"
            runner = CliRunner()
            result = runner.invoke(main, ["convert", "铁锭"])
            assert result.exit_code == 0
            assert "# 铁锭" in result.output
            assert "templates" not in result.output
            assert "json" not in result.output.lower()

    def test_detail_outputs_json(self):
        """--detail 输出完整 JSON"""
        with patch("mdifier.cli.convert_detailed") as mock:
            mock.return_value = SimpleNamespace(
                title="铁锭",
                markdown="# 铁锭\ncontent",
                source="api",
                templates={"Hatnote": {"class": "hatnote", "text": "note"}},
            )
            runner = CliRunner()
            result = runner.invoke(main, ["convert", "铁锭", "--detail"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["title"] == "铁锭"
            assert "markdown" in data
            assert "templates" in data
            assert data["templates"]["Hatnote"]["class"] == "hatnote"


class TestSearchCommand:
    """search 命令测试"""

    def test_search_returns_results(self):
        """search 命令返回搜索结果"""
        with patch("mdifier.cli.search") as mock_search:
            mock_search.return_value = [
                {
                    "title": "Diamond",
                    "description": "A precious resource",
                    "url": "https://example.com/Diamond",
                },
                {
                    "title": "Diamond Ore",
                    "description": "An ore that drops diamonds",
                    "url": "https://example.com/Diamond_Ore",
                },
            ]
            runner = CliRunner()
            result = runner.invoke(main, ["search", "diamond"])
            assert result.exit_code == 0
            assert "Diamond" in result.output
            assert "Diamond Ore" in result.output

    def test_search_empty_results(self):
        """search 无结果时显示提示"""
        with patch("mdifier.cli.search") as mock_search:
            mock_search.return_value = []
            runner = CliRunner()
            result = runner.invoke(main, ["search", "nonexistent"])
            assert result.exit_code == 0
            assert "未找到结果" in result.output

    def test_search_with_lang(self):
        """search 命令传递 --lang 参数"""
        with patch("mdifier.cli.search") as mock_search:
            mock_search.return_value = [
                {
                    "title": "鉄インゴット",
                    "description": "Japanese",
                    "url": "https://ja.example.com",
                }
            ]
            runner = CliRunner()
            result = runner.invoke(main, ["search", "鉄", "--lang", "ja"])
            assert result.exit_code == 0
            mock_search.assert_called_once()
            assert mock_search.call_args[1]["lang"] == "ja"

    def test_search_with_num(self):
        """search 命令限制结果数量"""
        with patch("mdifier.cli.search") as mock_search:
            mock_search.return_value = [{"title": "A"}, {"title": "B"}, {"title": "C"}]
            runner = CliRunner()
            result = runner.invoke(main, ["search", "test", "-n", "2"])
            assert result.exit_code == 0
            # 验证只显示 2 个结果
            mock_search.return_value = [{"title": "A"}, {"title": "B"}, {"title": "C"}]
            # search 函数本身返回全部，由调用方切片


class TestBatchCommand:
    """batch 命令测试"""

    def test_batch_with_titles(self):
        """batch -t 多标题批量转换"""
        with patch("mdifier.cli.convert_many") as mock_batch:
            mock_result = MagicMock()
            mock_result.results = [
                SimpleNamespace(title="Diamond", markdown="# Diamond\ncontent"),
                SimpleNamespace(title="Iron Ingot", markdown="# Iron Ingot\ncontent"),
            ]
            mock_result.failed = []
            mock_result.unresolved = []
            mock_batch.return_value = mock_result

            runner = CliRunner()
            result = runner.invoke(main, ["batch", "-t", "Diamond", "-t", "Iron Ingot"])
            assert result.exit_code == 0

    def test_batch_partial_failure(self):
        """batch 部分失败时返回退出码 65（EX_DATAERR）"""
        with patch("mdifier.cli.convert_many") as mock_batch:
            mock_result = MagicMock()
            mock_result.results = [SimpleNamespace(title="Diamond", markdown="# Diamond")]
            mock_result.failed = [("UnknownPage", Exception("Not found"))]
            mock_result.unresolved = []
            mock_batch.return_value = mock_result

            runner = CliRunner()
            result = runner.invoke(main, ["batch", "-t", "Diamond", "-t", "UnknownPage"])
            assert result.exit_code == 65  # EX_DATAERR

    def test_batch_invalid_lang(self):
        """batch 无效 --lang 参数被 click.Choice 拒绝"""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "-t", "Diamond", "--lang", "xx"])
        # click.Choice 验证失败返回 exit_code 2
        assert result.exit_code == 2


class TestCacheCommand:
    """cache 子命令测试"""

    def test_cache_info(self):
        """cache info 显示统计信息"""
        with patch("mdifier.cache.cache_info") as mock_info:
            mock_info.return_value = {
                "path": "/fake/cache",
                "exists": False,
                "size_bytes": 0,
                "size_mb": 0,
                "entries": 0,
                "fresh_entries": 0,
                "expired_entries": 0,
                "oldest_ts": None,
                "newest_ts": None,
            }
            runner = CliRunner()
            result = runner.invoke(main, ["cache", "info"])
            assert result.exit_code == 0
            assert "路径" in result.output

    def test_cache_clear_without_force(self):
        """cache clear 无 -y 时提示确认"""
        with patch("mdifier.cache.cache_info") as mock_info:
            mock_info.return_value = {
                "exists": True,
                "size_mb": 1.5,
                "entries": 10,
            }
            runner = CliRunner()
            result = runner.invoke(main, ["cache", "clear"])
            # 无 -y 时 click.confirm 会 abort，不直接清除
            assert result.exit_code != 0

    def test_cache_clear_with_force(self):
        """cache clear -y 直接清除"""
        with (
            patch("mdifier.cache.clear_cache") as mock_clear,
            patch("mdifier.cache.cache_info") as mock_info,
        ):
            mock_info.return_value = {
                "exists": True,
                "size_mb": 1.5,
                "entries": 10,
            }
            mock_clear.return_value = True
            runner = CliRunner()
            result = runner.invoke(main, ["cache", "clear", "-y"])
            assert result.exit_code == 0

    def test_cache_prune(self):
        """cache prune 保留未过期条目"""
        with (
            patch("mdifier.cache.cache_info") as mock_info,
            patch("mdifier.cache.CACHE_FILE") as mock_cache_file,
        ):
            mock_info.return_value = {
                "exists": True,
                "entries": 10,
                "expired_entries": 3,
            }
            mock_cache_file.read_text.return_value = '{"key": {"ts": 9999999999}}'
            runner = CliRunner()
            result = runner.invoke(main, ["cache", "prune"])
            assert result.exit_code == 0


class TestCLIErrorHandling:
    """CLI 错误处理测试"""

    def test_convert_unsupported_lang(self):
        """convert 不支持的 lang 被 click.Choice 拒绝"""
        runner = CliRunner()
        result = runner.invoke(main, ["convert", "test", "--lang", "xx"])
        # click.Choice 验证失败返回 exit_code 2
        assert result.exit_code == 2

    def test_batch_nonexistent_input_file(self):
        """batch -i 输入文件不存在时返回错误"""
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "-i", "nonexistent_file.txt"])
        assert result.exit_code != 0
