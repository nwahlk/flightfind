# tests/test_feizhu_crawler.py
from src.base_crawler import FlightCrawler
from src.feizhu_crawler import FeizhuCrawler


def test_feizhu_crawler_inherits_from_base():
    """FeizhuCrawler should inherit from FlightCrawler"""
    assert issubclass(FeizhuCrawler, FlightCrawler)


def test_feizhu_crawler_has_source_attribute():
    """FeizhuCrawler should have source = 'feizhu'"""
    assert hasattr(FeizhuCrawler, "source")
    assert FeizhuCrawler.source == "feizhu"


def test_feizhu_crawler_init_preserves_parameters():
    """FeizhuCrawler __init__ should preserve headless parameter"""
    crawler = FeizhuCrawler(headless=False)
    assert crawler.headless is False
    assert crawler.playwright is None


def test_feizhu_crawler_init_defaults():
    """FeizhuCrawler __init__ should use default headless=True"""
    crawler = FeizhuCrawler()
    assert crawler.headless is True


def test_get_feizhu_city_code():
    """Test city code mapping for major cities"""
    from src.feizhu_crawler import get_feizhu_city_code

    assert get_feizhu_city_code("北京") == "BJS"
    assert get_feizhu_city_code("上海") == "SHA"
    assert get_feizhu_city_code("广州") == "CAN"
    assert get_feizhu_city_code("深圳") == "SZX"
    assert get_feizhu_city_code("Unknown") == "Unknown"
