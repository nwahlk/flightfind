# tests/test_ctrip_crawler.py
import pytest
from pathlib import Path
from src.crawler import CtripCrawler
from src.base_crawler import FlightCrawler


def test_ctrip_crawler_inherits_from_base():
    """CtripCrawler should inherit from FlightCrawler"""
    assert issubclass(CtripCrawler, FlightCrawler)


def test_ctrip_crawler_has_source_attribute():
    """CtripCrawler should have source = 'ctrip'"""
    assert hasattr(CtripCrawler, 'source')
    assert CtripCrawler.source == "ctrip"


def test_ctrip_crawler_init_preserves_parameters():
    """CtripCrawler __init__ should preserve its specific parameters"""
    crawler = CtripCrawler(
        headless=False,
        debug_save_html=True,
        debug_html_path=Path("/tmp/test"),
        page_load_timeout=30000
    )
    assert crawler.headless is False
    assert crawler.debug_save_html is True
    assert crawler.debug_html_path.name == "test"
    assert crawler.page_load_timeout == 30000
