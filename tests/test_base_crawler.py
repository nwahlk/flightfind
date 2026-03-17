# tests/test_base_crawler.py
import pytest
from src.base_crawler import FlightCrawler

def test_cannot_instantiate_base_class():
    """Cannot instantiate abstract class"""
    with pytest.raises(TypeError):
        crawler = FlightCrawler()
