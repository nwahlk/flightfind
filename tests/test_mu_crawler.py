# tests/test_mu_crawler.py
"""Tests for China Eastern Airlines (MU) crawler."""

from src.base_crawler import FlightCrawler
from src.mu_crawler import MuCrawler, get_mu_city_code


def test_mu_crawler_inherits_from_base():
    """MuCrawler should inherit from FlightCrawler"""
    assert issubclass(MuCrawler, FlightCrawler)


def test_mu_crawler_has_source_attribute():
    """MuCrawler should have source = 'mu'"""
    assert hasattr(MuCrawler, "source")
    assert MuCrawler.source == "mu"


def test_mu_crawler_init_preserves_parameters():
    """MuCrawler __init__ should preserve headless parameter"""
    crawler = MuCrawler(headless=False)
    assert crawler.headless is False
    assert crawler.playwright is None


def test_mu_crawler_init_defaults():
    """MuCrawler __init__ should use default headless=True"""
    crawler = MuCrawler()
    assert crawler.headless is True


def test_get_mu_city_code():
    """Test city code mapping for major cities"""
    assert get_mu_city_code("北京") == "BJS"
    assert get_mu_city_code("上海") == "SHA"
    assert get_mu_city_code("广州") == "CAN"
    assert get_mu_city_code("深圳") == "SZX"
    assert get_mu_city_code("成都") == "CTU"
    assert get_mu_city_code("杭州") == "HGH"
    assert get_mu_city_code("西安") == "XIY"
    assert get_mu_city_code("重庆") == "CKG"
    # 未知城市返回原值
    assert get_mu_city_code("未知城市") == "未知城市"
