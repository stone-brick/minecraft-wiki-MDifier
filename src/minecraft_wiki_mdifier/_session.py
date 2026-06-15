"""
共享 HTTP Session 工厂函数

提供统一的 HTTP Session 配置（重试机制、User-Agent），避免在多个模块中重复定义。
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import __version__

USER_AGENT = f"Minecraft-Wiki-MDifier/{__version__} (Python Wiki Converter)"


def create_session() -> requests.Session:
    """
    创建配置好的 HTTP Session

    配置项：
    - User-Agent 头
    - 重试机制：3 次重试，指数退避（0.5s/1s/2s），对 429/500/502/503/504 生效

    Returns:
        配置好的 requests.Session 实例
    """
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist={429, 500, 502, 503, 504},
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session
