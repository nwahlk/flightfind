# tests/test_zh_crawler.py
"""Tests for Shenzhen Airlines (ZH) crawler."""

from src.base_crawler import FlightCrawler
from src.zh_crawler import ZhCrawler, get_zh_city_code


def test_zh_crawler_inherits_from_base():
    """ZhCrawler should inherit from FlightCrawler"""
    assert issubclass(ZhCrawler, FlightCrawler)


def test_zh_crawler_has_source_attribute():
    """ZhCrawler should have source = 'zh'"""
    assert hasattr(ZhCrawler, "source")
    assert ZhCrawler.source == "zh"


def test_zh_crawler_init_preserves_parameters():
    """ZhCrawler __init__ should preserve headless parameter"""
    crawler = ZhCrawler(headless=False)
    assert crawler.headless is False
    assert crawler.playwright is None


def test_zh_crawler_init_defaults():
    """ZhCrawler __init__ should use default headless=True"""
    crawler = ZhCrawler()
    assert crawler.headless is True


def test_get_zh_city_code():
    """Test city code mapping for major cities"""
    assert get_zh_city_code("深圳") == "SZX"
    assert get_zh_city_code("北京") == "PEK"
    assert get_zh_city_code("上海") == "SHA"
    assert get_zh_city_code("广州") == "CAN"
    assert get_zh_city_code("成都") == "CTU"
    assert get_zh_city_code("杭州") == "HGH"
    assert get_zh_city_code("西安") == "XIY"
    assert get_zh_city_code("重庆") == "CKG"
    # 未知城市返回原值
    assert get_zh_city_code("未知城市") == "未知城市"
