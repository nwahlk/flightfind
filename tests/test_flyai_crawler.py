"""FlyAI 爬虫单元测试。"""

import asyncio
import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import FlyAIConfig, Route, DateConfig
from src.exceptions import CrawlerError, ParseError
from src.flyai_crawler import FlyAICrawler, FlyAITrainCrawler


# ── 构造 mock subprocess 的辅助 ──────────────────────────────────────────────

def _mock_proc(stdout: str = "", stderr: str = "", returncode: int = 0):
    """创建一个模拟子进程对象。"""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout.encode("utf-8"), stderr.encode("utf-8")))
    return proc


def _sample_flight_json(adult_price="¥400.0", flight_no="CA1883", airline="国航"):
    """生成一条模拟的 FlyAI 航班 JSON。"""
    return json.dumps({
        "status": 0,
        "message": "success",
        "data": {
            "itemList": [{
                "adultPrice": adult_price,
                "journeys": [{
                    "journeyType": "直达",
                    "segments": [{
                        "depCityName": "北京",
                        "depStationName": "首都国际机场",
                        "depDateTime": "2026-04-15 21:00:00",
                        "arrCityName": "上海",
                        "arrStationName": "浦东国际机场",
                        "arrDateTime": "2026-04-15 23:20:00",
                        "duration": "140分钟",
                        "marketingTransportName": airline,
                        "marketingTransportNo": flight_no,
                        "seatClassName": "经济舱",
                    }],
                    "totalDuration": "140分钟",
                }],
                "jumpUrl": "https://example.com/booking",
            }],
        },
    })


def _sample_train_json(price="¥553.0", train_no="G100", train_type="高速动车"):
    """生成一条模拟的 FlyAI 高铁 JSON。"""
    return json.dumps({
        "status": 0,
        "message": "success",
        "data": {
            "itemList": [{
                "price": price,
                "trainNo": train_no,
                "trainType": train_type,
                "fromStationName": "深圳北",
                "toStationName": "上海虹桥",
                "startTime": "2026-05-20 08:00:00",
                "endTime": "2026-05-20 15:30:00",
                "duration": "7小时30分钟",
                "seatClassName": "二等座",
                "jumpUrl": "https://example.com/train",
            }],
        },
    })


def _sample_route(from_city="北京", to_city="上海", threshold=800, dates=None):
    """创建测试用 Route 对象。"""
    if dates is None:
        dates = [date(2026, 4, 15)]
    return Route(
        from_city=from_city,
        to_city=to_city,
        low_price_threshold=threshold,
        dates=DateConfig(mode="absolute", absolute_dates=dates),
    )


# ── _parse_price ────────────────────────────────────────────────────────────

class TestParsePrice:
    def test_yuan_symbol(self):
        assert FlyAICrawler._parse_price("¥400.0") == 400

    def test_numeric_only(self):
        assert FlyAICrawler._parse_price("400.0") == 400

    def test_integer_string(self):
        assert FlyAICrawler._parse_price("¥1234") == 1234

    def test_empty_string(self):
        assert FlyAICrawler._parse_price("") == 0

    def test_invalid_string(self):
        assert FlyAICrawler._parse_price("abc") == 0

    def test_none_like(self):
        assert FlyAICrawler._parse_price(None) == 0  # type: ignore[arg-type]


# ── _parse_flight_item ──────────────────────────────────────────────────────

class TestParseFlightItem:
    def test_success(self):
        crawler = FlyAICrawler()
        item = json.loads(_sample_flight_json())["data"]["itemList"][0]
        record = crawler._parse_flight_item(item, "北京", "上海", date(2026, 4, 15))

        assert record is not None
        assert record["source"] == "flyai"
        assert record["flight_no"] == "CA1883"
        assert record["airline"] == "国航"
        assert record["price"] == 400
        assert record["departure_airport"] == "首都国际机场"
        assert record["arrival_airport"] == "浦东国际机场"
        assert record["metadata"]["duration"] == "140分钟"
        assert record["metadata"]["seat_class"] == "经济舱"
        assert record["metadata"]["booking_url"] == "https://example.com/booking"

    def test_missing_segments(self):
        crawler = FlyAICrawler()
        item = {"adultPrice": "¥100", "journeys": []}
        assert crawler._parse_flight_item(item, "北京", "上海", date(2026, 4, 15)) is None

    def test_missing_journeys(self):
        crawler = FlyAICrawler()
        item = {"adultPrice": "¥100"}
        assert crawler._parse_flight_item(item, "北京", "上海", date(2026, 4, 15)) is None

    def test_malformed_item_no_crash(self):
        crawler = FlyAICrawler()
        assert crawler._parse_flight_item({}, "北京", "上海", date(2026, 4, 15)) is None


# ── _search_single_date ─────────────────────────────────────────────────────

class TestSearchSingleDate:
    @pytest.mark.asyncio
    async def test_configured_credentials_are_passed_to_cli_env(self):
        crawler = FlyAICrawler(
            flyai_config=FlyAIConfig(api_key="sk-official", sign_secret="sign-secret")
        )
        mock_proc = _mock_proc(stdout=_sample_flight_json())

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc) as create_proc:
            await crawler._search_single_date("北京", "上海", date(2026, 4, 15))

        env = create_proc.call_args.kwargs["env"]
        assert env["FLYAI_API_KEY"] == "sk-official"
        assert env["FLYAI_SIGN_SECRET"] == "sign-secret"

    @pytest.mark.asyncio
    async def test_success(self):
        crawler = FlyAICrawler()
        mock_proc = _mock_proc(stdout=_sample_flight_json())

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            results = await crawler._search_single_date("北京", "上海", date(2026, 4, 15))

        assert len(results) == 1
        assert results[0]["flight_no"] == "CA1883"

    @pytest.mark.asyncio
    async def test_empty_results(self):
        crawler = FlyAICrawler()
        empty_json = json.dumps({"status": 0, "message": "success", "data": {"itemList": []}})
        mock_proc = _mock_proc(stdout=empty_json)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            results = await crawler._search_single_date("北京", "上海", date(2026, 4, 15))

        assert results == []

    @pytest.mark.asyncio
    async def test_cli_error_nonzero_exit(self):
        crawler = FlyAICrawler()
        mock_proc = _mock_proc(stderr="command not found", returncode=1)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            with pytest.raises(CrawlerError, match="FlyAI CLI 错误"):
                await crawler._search_single_date("北京", "上海", date(2026, 4, 15))

    @pytest.mark.asyncio
    async def test_api_error_status(self):
        crawler = FlyAICrawler()
        error_json = json.dumps({"status": 1, "message": "参数错误"})
        mock_proc = _mock_proc(stdout=error_json)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            with pytest.raises(CrawlerError, match="参数错误"):
                await crawler._search_single_date("北京", "上海", date(2026, 4, 15))

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        crawler = FlyAICrawler()
        mock_proc = _mock_proc(stdout="not json at all")

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            with pytest.raises(ParseError, match="无效 JSON"):
                await crawler._search_single_date("北京", "上海", date(2026, 4, 15))

    @pytest.mark.asyncio
    async def test_timeout(self):
        crawler = FlyAICrawler()
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            with pytest.raises(CrawlerError, match="超时"):
                await crawler._search_single_date("北京", "上海", date(2026, 4, 15))

    @pytest.mark.asyncio
    async def test_cli_not_found(self):
        crawler = FlyAICrawler()

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, side_effect=FileNotFoundError):
            with pytest.raises(CrawlerError, match="未安装"):
                await crawler._search_single_date("北京", "上海", date(2026, 4, 15))


# ── init / close ────────────────────────────────────────────────────────────

class TestLifecycle:
    @pytest.mark.asyncio
    async def test_init_success(self):
        crawler = FlyAICrawler()
        mock_proc = _mock_proc(stdout="")

        with patch("src.flyai_crawler.shutil.which", return_value="/usr/bin/flyai"), \
             patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            await crawler.init()
            assert crawler._flyai_cmd == "/usr/bin/flyai"

    @pytest.mark.asyncio
    async def test_init_cli_missing(self):
        crawler = FlyAICrawler()

        with patch("src.flyai_crawler.shutil.which", return_value=None), \
             patch("src.flyai_crawler.Path.exists", return_value=False):
            with pytest.raises(CrawlerError, match="未安装"):
                await crawler.init()

    @pytest.mark.asyncio
    async def test_close_noop(self):
        crawler = FlyAICrawler()
        await crawler.close()  # 不应抛出异常


# ── search_flights ──────────────────────────────────────────────────────────

class TestSearchFlights:
    @pytest.mark.asyncio
    async def test_single_date(self):
        crawler = FlyAICrawler()
        route = _sample_route()
        mock_proc = _mock_proc(stdout=_sample_flight_json())

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            results = await crawler.search_flights(route)

        assert len(results) == 1


class TestTrainCrawler:
    def test_parse_train_item_success(self):
        crawler = FlyAITrainCrawler()
        item = json.loads(_sample_train_json())["data"]["itemList"][0]
        record = crawler._parse_train_item(item, "深圳", "上海", date(2026, 5, 20))

        assert record is not None
        assert record["source"] == "flyai_train"
        assert record["flight_no"] == "G100"
        assert record["airline"] == "高速动车"
        assert record["price"] == 553
        assert record["departure_airport"] == "深圳北"
        assert record["arrival_airport"] == "上海虹桥"
        assert record["metadata"]["transport_type"] == "train"
        assert record["metadata"]["seat_class"] == "二等座"

    @pytest.mark.asyncio
    async def test_search_train_single_date(self):
        crawler = FlyAITrainCrawler()
        route = _sample_route(from_city="深圳", to_city="上海", dates=[date(2026, 5, 20)])
        mock_proc = _mock_proc(stdout=_sample_train_json())

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc) as create_proc:
            results = await crawler.search_flights(route)

        assert len(results) == 1
        assert results[0]["flight_no"] == "G100"
        args = create_proc.call_args.args
        assert args[1] == "search-train"
        assert "--origin" in args
        assert "--destination" in args
        assert "--dep-date" in args

    @pytest.mark.asyncio
    async def test_multiple_dates(self):
        crawler = FlyAICrawler()
        route = _sample_route(dates=[date(2026, 4, 15), date(2026, 4, 16)])
        mock_proc = _mock_proc(stdout=_sample_flight_json())

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            results = await crawler.search_flights(route)

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_failure_skipped(self):
        """单日期搜索失败不应中断其他日期。"""
        crawler = FlyAICrawler()
        route = _sample_route(dates=[date(2026, 4, 15), date(2026, 4, 16)])

        call_count = 0

        async def mock_subproc(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise CrawlerError("模拟失败")
            return _mock_proc(stdout=_sample_flight_json())

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, side_effect=mock_subproc):
            results = await crawler.search_flights(route)

        assert len(results) == 1
