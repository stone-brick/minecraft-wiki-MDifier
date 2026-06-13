"""
颜色/格式化规范

将各系统的颜色代码统一转为语义化标签。
"""


class MinecraftColorFormatter:
    """Minecraft & 格式代码 → 语义化标签

    将 `&e镶铆盔甲纹饰&/&7锻造模板&r` 转为
    `[yellow]镶铆盔甲纹饰\n[gray]锻造模板[reset]`
    """

    COLORS = {
        "0": "black",
        "1": "dark_blue",
        "2": "dark_green",
        "3": "dark_aqua",
        "4": "dark_red",
        "5": "dark_purple",
        "6": "gold",
        "7": "gray",
        "8": "dark_gray",
        "9": "blue",
        "a": "green",
        "b": "aqua",
        "c": "red",
        "d": "light_purple",
        "e": "yellow",
        "f": "white",
        "g": "minecoin_gold",
        "h": "material_quartz",
        "i": "material_iron",
        "p": "material_gold",
        "q": "material_diamond",
        "s": "material_redstone",
        "t": "material_lapis",
        "u": "material_amethyst",
        "v": "material_copper",
        "x": "material_netherite",
        "y": "material_emerald",
        "z": "material_resin",
    }
    FORMATS = {
        "k": "obfuscated",
        "l": "bold",
        "m": "strikethrough",
        "n": "underlined",
        "o": "italic",
        "r": "reset",
    }
    PATTERN = r"&([0-9a-zA-Z])"

    def clean(self, text: str) -> str:
        """将 & 代码转为 [tag] 形式"""
        if not text:
            return text

        import re

        # 把 &/ 替换为换行
        text = text.replace("&/", "\n")
        # 双斜杠视为空格
        text = re.sub(r"/+", " ", text)

        # 把 &code 替换为 [code] 前缀
        text = re.sub(self.PATTERN, self._replace_code, text)

        # 清理多余空白
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text).strip()
        return text

    def _replace_code(self, match):
        code = match.group(1).lower()
        if code in self.COLORS:
            return f"[{self.COLORS[code]}]"
        if code in self.FORMATS:
            return f"[{self.FORMATS[code]}]"
        return ""
