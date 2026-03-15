"""
FlightFind 异常定义
"""


class FlightFindError(Exception):
    """基础异常"""
    pass


class ConfigError(FlightFindError):
    """配置错误"""
    pass


class DatabaseError(FlightFindError):
    """数据库错误"""
    pass


class CrawlerError(FlightFindError):
    """爬虫错误"""
    pass


class BrowserCrashError(CrawlerError):
    """浏览器崩溃错误"""
    pass


class NetworkError(CrawlerError):
    """网络错误"""
    pass


class TimeoutError(CrawlerError):
    """超时错误"""
    pass


class ParseError(CrawlerError):
    """解析错误"""
    pass


class AntiBotError(CrawlerError):
    """反爬检测"""
    pass


class NotifierError(FlightFindError):
    """通知错误"""
    pass


class RetryExhaustedError(FlightFindError):
    """重试耗尽"""
    pass
