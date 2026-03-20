"""Shared utility helpers."""

import logging
import sys
from pathlib import Path


def setup_logging(log_file: Path = None, level: int = logging.INFO) -> logging.Logger:
    """Configure the project logger."""

    logger = logging.getLogger("flightfind")
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def retry_with_backoff(max_attempts: int = 3, base_delay: float = 1.0):
    """Retry async functions with exponential backoff."""

    def decorator(func):
        import asyncio
        import random

        async def wrapper(*args, **kwargs):
            from src.exceptions import AntiBotError
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except AntiBotError:
                    raise  # 风控异常不重试
                except Exception:
                    if attempt == max_attempts - 1:
                        raise
                    delay = base_delay * (2 ** attempt) + random.random()
                    await asyncio.sleep(delay)
            return None

        return wrapper

    return decorator


logger = logging.getLogger("flightfind")
