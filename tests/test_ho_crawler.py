# tests/test_ho_crawler.py
"""Tests for Juneyao Air (HO) crawler."""

from src.base_crawler import FlightCrawler
from src.ho_crawler import HoCrawler, get_ho_city_code


def test_ho_crawler_inherits_from_base():
    """HoCrawler should inherit from FlightCrawler"""
    assert issubclass(HoCrawler, FlightCrawler)


def test_ho_crawler_has_source_attribute():
    """HoCrawler should have source = 'ho'"""
    assert hasattr(HoCrawler, "source")
    assert HoCrawler.source == "ho"


def test_ho_crawler_init_preserves_parameters():
    """HoCrawler __init__ should preserve headless parameter"""
    crawler = HoCrawler(headless=False)
    assert crawler.headless is False
    assert crawler.playwright is None


def test_ho_crawler_init_defaults():
    """HoCrawler __init__ should use default headless=True"""
    crawler = HoCrawler()
    assert crawler.headless is True


def test_get_ho_city_code():
    """测试城市代码转换"""
    assert get_ho_city_code("上海") == "SHA"
    assert get_ho_city_code("北京") == "BJS"
    assert get_ho_city_code("深圳") == "SZX"
    assert get_ho_city_code("广州") == "CAN"
    assert get_ho_city_code("成都") == "CTU"
    assert get_ho_city_code("杭州") == "HGH"
    assert get_ho_city_code("西安") == "XIY"
    assert get_ho_city_code("重庆") == "CKG"
    # 未知城市返回原值
    assert get_ho_city_code("未知城市") == "未知城市"
