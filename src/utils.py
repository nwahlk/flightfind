"""Shared utility helpers."""

import logging
import re
import sys
from pathlib import Path
from typing import List, Tuple


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
                    raise
                except Exception:
                    if attempt == max_attempts - 1:
                        raise
                    delay = base_delay * (2 ** attempt) + random.random()
                    await asyncio.sleep(delay)
            return None

        return wrapper

    return decorator


logger = logging.getLogger("flightfind")

DOM_TEXT_WALKER_JS = r'''(splitMode) => {
    const walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_TEXT,
        { acceptNode: node => {
            const parent = node.parentElement;
            if (!parent) return NodeFilter.FILTER_REJECT;
            const tag = parent.tagName.toLowerCase();
            if (['script','style','noscript'].includes(tag)) return NodeFilter.FILTER_REJECT;
            const text = node.textContent.trim();
            if (!text) return NodeFilter.FILTER_REJECT;
            return NodeFilter.FILTER_ACCEPT;
        }}
    );

    const texts = [];
    let node;
    while (node = walker.nextNode()) {
        texts.push(node.textContent.trim());
    }

    const blocks = [];
    let current = [];
    const delimiter = splitMode || '订票';
    for (const text of texts) {
        if (text === delimiter) {
            if (current.length > 3) blocks.push(current);
            current = [];
        } else {
            current.push(text);
        }
    }
    if (current.length > 2) blocks.push(current);
    return blocks;
}'''

_RE_WS = re.compile(r"[\xa0\u3000]+")
_RE_TIME = re.compile(r"^\d{2}:\d{2}$")
_RE_PRICE_SYMBOL = re.compile(r"(\d{3,5})\s*起")


def clean_dom_texts(block: List[str]) -> List[str]:
    return [text for text in (re.sub(_RE_WS, "", item).strip() for item in block) if text]


def extract_times(texts: List[str]) -> Tuple[str, str]:
    times = [text for text in texts if _RE_TIME.match(text)]
    return (times[0] if times else "", times[1] if len(times) > 1 else "")


def extract_airports(texts: List[str]) -> Tuple[str, str]:
    airports = [text for text in texts if "机场" in text]
    return (airports[0] if airports else "", airports[1] if len(airports) > 1 else "")


def extract_price_forward(texts: List[str]) -> int:
    for index, text in enumerate(texts):
        if text in ("¥", "￥") and index + 1 < len(texts):
            try:
                return int(texts[index + 1])
            except ValueError:
                pass
            break
    for text in texts:
        match = _RE_PRICE_SYMBOL.search(text)
        if match:
            return int(match.group(1))
    return 0
