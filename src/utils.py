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

# ── DOM 文本块解析共享常量 ──

# JS TreeWalker 文本收集脚本（三个爬虫共用）
# 参数: splitMode="订票" 按按钮分割 | splitMode="flight_no" 按航班号分割
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
    if (splitMode === 'flight_no') {
        for (const text of texts) {
            if (/^[A-Z]{2}\d{3,4}$/.test(text)) {
                if (current.length > 2) blocks.push([...current, text]);
                current = [];
            } else {
                current.push(text);
            }
        }
    } else {
        const delimiter = splitMode || '订票';
        for (const text of texts) {
            if (text === delimiter) {
                if (current.length > 3) blocks.push(current);
                current = [];
            } else {
                current.push(text);
            }
        }
    }
    if (current.length > 2) blocks.push(current);
    return blocks;
}'''

# 预编译正则
_RE_WS = re.compile(r"[\xa0\u3000]+")
_RE_TIME = re.compile(r"^\d{2}:\d{2}$")
_RE_PRICE_SYMBOL = re.compile(r"(\d{3,5})\s*起")
_RE_TERMINAL = re.compile(r"^T\d$")


def clean_dom_texts(block: List[str]) -> List[str]:
    """清理 DOM 文本块：合并空白字符，过滤空串"""
    return [t for t in (re.sub(_RE_WS, "", x).strip() for x in block) if t]


def extract_times(texts: List[str]) -> Tuple[str, str]:
    """从文本列表中提取出发/到达时间"""
    times = [t for t in texts if _RE_TIME.match(t)]
    return (times[0] if times else "", times[1] if len(times) > 1 else "")


def extract_airports(texts: List[str]) -> Tuple[str, str]:
    """从文本列表中提取出发/到达机场（包含"机场"的文本）"""
    airports = [t for t in texts if "机场" in t]
    return (airports[0] if airports else "", airports[1] if len(airports) > 1 else "")


def extract_terminals(texts: List[str]) -> List[str]:
    """从文本列表中提取航站楼"""
    return [t for t in texts if _RE_TERMINAL.match(t)]


def extract_price_forward(texts: List[str]) -> int:
    """正向查找价格：先找 ¥ 后面的数字，再找"数字起"格式"""
    for i, text in enumerate(texts):
        if text in ("¥", "￥") and i + 1 < len(texts):
            try:
                return int(texts[i + 1])
            except ValueError:
                pass
            break
    for text in texts:
        m = _RE_PRICE_SYMBOL.search(text)
        if m:
            return int(m.group(1))
    return 0


def extract_price_backward(texts: List[str]) -> int:
    """反向查找价格：从末尾往前找 ¥ 或"数字起"格式"""
    for i in range(len(texts) - 1, -1, -1):
        if texts[i] in ("¥", "￥") and i + 1 < len(texts):
            try:
                return int(texts[i + 1])
            except ValueError:
                pass
            break
        m = re.search(r"(\d{3,5})\s*起$", texts[i])
        if m:
            return int(m.group(1))
            break
    return 0
