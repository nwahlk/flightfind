"""
工具函数
"""

import logging
import sys
from pathlib import Path


def setup_logging(log_file: Path = None, level: int = logging.INFO) -> logging.Logger:
    """配置日志"""
    logger = logging.getLogger("flightfind")
    logger.setLevel(level)

    # 清除已有处理器
    logger.handlers.clear()

    # 格式化
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件输出
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def retry_with_backoff(max_attempts: int = 3, base_delay: float = 1.0):
    """重试装饰器"""
    def decorator(func):
        import asyncio
        import random

        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    delay = base_delay * (2 ** attempt) + random.random()
                    await asyncio.sleep(delay)
            return None
        return wrapper
    return decorator
