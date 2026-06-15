"""
共享验证函数

提供语言验证等通用验证逻辑，避免多处重复定义。
"""

from minecraft_wiki_mdifier.exceptions import InvalidInputError


def validate_lang(lang: str | None) -> None:
    """
    验证语言代码是否支持

    Args:
        lang: 语言代码

    Raises:
        InvalidInputError: 不支持的语言代码
    """
    # 延迟导入避免循环依赖
    from minecraft_wiki_mdifier.wiki import LANG_CONFIG

    if lang is not None and lang not in LANG_CONFIG:
        raise InvalidInputError(
            f"Unsupported language: {lang}. Available: {list(LANG_CONFIG.keys())}"
        )
