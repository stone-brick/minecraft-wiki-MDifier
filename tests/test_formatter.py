"""测试 MinecraftColorFormatter"""

from minecraft_wiki_mdifier.formatters import MinecraftColorFormatter


class TestMinecraftColorFormatter:
    def setup_method(self):
        self.f = MinecraftColorFormatter()

    def test_color_codes(self):
        """颜色代码：&0-9, &a-f 转为 [name]"""
        assert self.f.clean("&e黄色") == "[yellow]黄色"
        assert self.f.clean("&a绿色&r") == "[green]绿色[reset]"

    def test_format_codes(self):
        """格式代码：&k-o, &r 转为 [name]"""
        assert self.f.clean("&l粗体") == "[bold]粗体"
        assert self.f.clean("&o斜体") == "[italic]斜体"

    def test_slash_newline(self):
        """&/ 替换为换行"""
        assert self.f.clean("a&/b") == "a\nb"

    def test_double_slash(self):
        """连续斜杠转为空格"""
        assert self.f.clean("a//b") == "a b"

    def test_unknown_code_removed(self):
        """非 ASCII 字符（不匹配正则）原样保留"""
        # 正则只匹配 [0-9a-zA-Z]，所以 & 后跟其他字符（如中文）
        # 的情况不会触发 replace，保留原样
        result = self.f.clean("&中文")
        assert result == "&中文"  # & 后跟非 ASCII 字符，原样保留

    def test_multi_space_collapsed(self):
        """多空白合并为单空格"""
        assert self.f.clean("a  b   c") == "a b c"

    def test_empty_input(self):
        """空输入返回空"""
        assert self.f.clean("") == ""
        assert self.f.clean(None) is None  # type: ignore[arg-type]

    def test_strip_whitespace(self):
        """首尾空白去除"""
        assert self.f.clean("  hello  ") == "hello"
