from datetime import date

from src.base_crawler import FlightCrawler
from src.config import DateConfig, Route
from src.spring_crawler import SpringCrawler, get_spring_city_code


def test_spring_crawler_inherits_from_base():
    assert issubclass(SpringCrawler, FlightCrawler)


def test_spring_crawler_has_source_attribute():
    assert SpringCrawler.source == "spring"


def test_get_spring_city_code_known_city():
    assert get_spring_city_code("深圳") == "SZX"
    assert get_spring_city_code("上海") == "SHA"


def test_build_urls():
    crawler = SpringCrawler()
    flight_date = date(2026, 5, 22)
    list_url = crawler._build_list_url("深圳", "上海", flight_date)
    calendar_url = crawler._build_calendar_url("深圳", "上海", flight_date)

    assert "SZX-SHA" in list_url
    assert "FDate=2026-05-22" in list_url
    assert calendar_url == "https://flights.ch.com/SZX-SHA/?FDate=2026-05-22"


def test_parse_spring_dom_block():
    crawler = SpringCrawler()
    route = Route(
        from_city="深圳",
        to_city="上海",
        low_price_threshold=800,
        dates=DateConfig(mode="absolute", absolute_dates=[date(2026, 5, 22)]),
    )
    block = [
        "春秋航空 9C7520",
        "空客320",
        "13:15",
        "宝安国际机场T3",
        "2小时20分",
        "15:35",
        "虹桥国际机场T1",
        "¥",
        "1460",
        "起",
        "订票",
    ]

    record = crawler._parse_spring_dom_block(block, route, date(2026, 5, 22))

    assert record is not None
    assert record["source"] == "spring"
    assert record["flight_no"] == "9C7520"
    assert record["airline"] == "春秋航空"
    assert record["price"] == 1460
    assert record["metadata"]["departure_time"] == "13:15"
