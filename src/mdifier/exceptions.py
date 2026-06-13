"""
自定义异常层级

按错误类型分类：
- InvalidInputError: 用户输入错误（lang、参数）
- FetchError: 网络/Wiki API 错误
  - PageNotFoundError: 404 / 解析缺失
  - WikiAPIError: API 返回异常结构
  - NetworkError: 网络层失败
"""

import requests


class MdifierError(Exception):
    """mdifier 异常的基类"""


class InvalidInputError(MdifierError, ValueError):
    """用户输入错误：lang 不支持、参数错误等"""


class FetchError(MdifierError, requests.RequestException):
    """网络层错误的基类"""


class NetworkError(FetchError):
    """网络连接失败、SSL 错误、超时"""


class WikiAPIError(FetchError):
    """Wiki API 返回异常结构"""


class PageNotFoundError(FetchError):
    """页面不存在（404 或 API 返回无 parse 字段）"""


class ConversionError(MdifierError):
    """Markdown 转换失败"""


class CacheError(MdifierError, OSError):
    """缓存文件读写失败"""
