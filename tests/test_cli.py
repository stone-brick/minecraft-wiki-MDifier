"""测试 CLI convert --detail"""

import json
from types import SimpleNamespace
from unittest.mock import patch

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
