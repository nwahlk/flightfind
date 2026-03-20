# tests/test_base_crawler.py
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from src.base_crawler import FlightCrawler


class ConcreteCrawler(FlightCrawler):
    """用于测试的具体爬虫实现"""

    source = "test"

    async def init(self):
        pass

    async def search_flights(self, route):
        return []

    async def close(self):
        pass


def test_crawler_default_options():
    """测试默认选项"""
    crawler = ConcreteCrawler()
    assert crawler.headless is True
    assert crawler.use_stealth is True
    assert crawler.mobile_mode is False
    assert crawler.cookie_manager is None


def test_crawler_custom_options():
    """测试自定义选项"""
    crawler = ConcreteCrawler(
        headless=False,
        use_stealth=False,
        mobile_mode=True,
        cookie_dir=Path("/tmp/cookies"),
    )
    assert crawler.headless is False
    assert crawler.use_stealth is False
    assert crawler.mobile_mode is True
    assert crawler.cookie_manager is not None


def test_get_browser_args():
    """测试获取浏览器参数"""
    crawler = ConcreteCrawler()
    args = crawler._get_browser_args()
    assert "--no-sandbox" in args
    assert "--disable-blink-features=AutomationControlled" in args


def test_get_context_options():
    """测试获取上下文选项"""
    crawler = ConcreteCrawler()
    options = crawler._get_context_options()
    assert "viewport" in options
    assert "user_agent" in options
    assert "zh-CN" in options["locale"]


@pytest.mark.asyncio
async def test_random_delay():
    """测试随机延迟"""
    crawler = ConcreteCrawler()
    import time
    start = time.time()
    await crawler._random_delay(0.1, 0.2)
    elapsed = time.time() - start
    assert 0.1 <= elapsed <= 0.3  # 允许一些误差


def test_cannot_instantiate_base_class():
    """Cannot instantiate abstract class"""
    with pytest.raises(TypeError):
        crawler = FlightCrawler()
