"""
吉祥航空 (Juneyao Airlines) 官网爬虫
URL格式: https://m.juneyaoair.com/flights/index.html#/flightList/0?arrCode=SHA&sendCode=SZX&depCityName=深圳&arrCityName=上海&departureDate=2026-04-03
"""

import asyncio
import logging
import random
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlencode

from playwright.async_api import ElementHandle, Page, async_playwright

from src.base_crawler import FlightCrawler
from src.city_codes import COMMON_CITY_CODE_MAP
from src.config import Route
from src.exceptions import BrowserCrashError, CrawlerError, ParseError
from src.flight_record import normalize_flight_record
from src.utils import retry_with_backoff

logger = logging.getLogger(__name__)


# 吉祥航空城市代码映射（使用共享映射）
JUNEYAO_CITY_CODE_MAP = COMMON_CITY_CODE_MAP

JUNEYAO_AIRLINE_NAME = "吉祥航空"


def get_juneyao_city_code(city_name: str) -> str:
    """获取吉祥航空城市代码"""
    return JUNEYAO_CITY_CODE_MAP.get(city_name, city_name)


def build_juneyao_url(from_city: str, to_city: str, flight_date: date) -> str:
    """构建吉祥航空搜索 URL"""
    from_code = get_juneyao_city_code(from_city)
    to_code = get_juneyao_city_code(to_city)

    params = {
        "flightType": "OW",  # 单程
        "tripType": "D",  # 直飞
        "arrCode": to_code,
        "sendCode": from_code,
        "arrCityName": to_city,
        "depCityName": from_city,
        "departureDate": flight_date.isoformat(),
        "returnDate": "",
        "queryType": "",
        "sendAirportCode": "",
        "arrAirportCode": "",
        "sendAirportName": "",
        "arrAirportName": "",
        "passengerType": "ADT",  # 成人
    }

    return f"https://m.juneyaoair.com/flights/index.html#/flightList/0?{urlencode(params)}"


class JuneyaoCrawler(FlightCrawler):
    """吉祥航空航班爬虫"""

    source = "juneyao"

    def __init__(self, headless: bool = True, cookie_dir: Path = None):
        super().__init__(
            headless=headless,
            use_stealth=True,
            mobile_mode=True,  # 使用移动端页面，不需要登录
            cookie_dir=cookie_dir or Path("data/cookies"),
        )
        self.playwright = None
        self.debug_path = Path("logs")
        self.debug_path.mkdir(parents=True, exist_ok=True)
        self._session_warmed = False

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def init(self) -> None:
        """初始化浏览器"""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=self._get_browser_args(),
            )

            # 使用移动端 viewport
            options = {
                "viewport": {"width": 375, "height": 812},
                "locale": "zh-CN",
                "timezone_id": "Asia/Shanghai",
                "user_agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/16.0 Mobile/15E148 Safari/604.1"
                ),
                "extra_http_headers": {
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            }
            self.context = await self.browser.new_context(**options)
            await self._apply_stealth_to_context()
            await self._load_cookies_to_context()
            logger.info("[juneyao] browser initialized")
        except Exception as exc:
            raise BrowserCrashError(f"juneyao browser init failed: {exc}") from exc

    @retry_with_backoff(max_attempts=3, base_delay=4.0)
    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        """搜索航班"""
        results: List[Dict[str, Any]] = []

        for index, flight_date in enumerate(sorted(route.dates.absolute_dates)):
            if index:
                # 吉祥航空风控相对宽松，但仍需间隔
                await self._random_delay(10.0, 20.0)

            try:
                logger.info(
                    "[juneyao] searching %s -> %s on %s",
                    route.from_city,
                    route.to_city,
                    flight_date,
                )
                flights = await self._search_single_date(route, flight_date)
                results.extend(flights)
                logger.info(
                    "[juneyao] found %d flights for %s -> %s",
                    len(flights),
                    route.from_city,
                    route.to_city,
                )
            except Exception as exc:
                logger.error(
                    "[juneyao] search failed for %s -> %s on %s: %s",
                    route.from_city,
                    route.to_city,
                    flight_date,
                    exc,
                )

        return results

    async def _search_single_date(
        self, route: Route, flight_date: date
    ) -> List[Dict[str, Any]]:
        """搜索单个日期的航班"""
        if not self.context:
            raise CrawlerError("juneyao browser context is not initialized")

        page = await self.context.new_page()

        try:
            url = build_juneyao_url(route.from_city, route.to_city, flight_date)
            logger.info("[juneyao] navigating to: %s", url)

            # 先访问首页建立 session
            await self._warm_session(page)

            # 访问航班列表页
            await self._random_delay(2.0, 3.0)
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # 等待页面加载
            await page.wait_for_timeout(random.randint(5000, 8000))

            # 检查是否有航班
            if await self._check_no_flights(page):
                logger.info("[juneyao] no flights found for %s", flight_date)
                return []

            # 检查是否被风控
            if await self._check_antibot(page):
                raise CrawlerError("juneyao page shows anti-bot detection")

            # 保存调试快照
            await self._save_debug_snapshot(page, route, flight_date, "list_page")

            # 解析航班
            flights = await self._parse_flights(page, route, flight_date)

            if not flights:
                raise ParseError("juneyao page did not yield any flights")

            return flights

        finally:
            await page.close()

    async def _warm_session(self, page: Page) -> None:
        """预热 session，访问首页"""
        if self._session_warmed:
            return

        try:
            await page.goto("https://m.juneyaoair.com/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(2000, 3000))

            # 处理隐私政策弹窗（如果有）
            try:
                agree_btn = await page.query_selector("text=同意并继续")
                if agree_btn:
                    await agree_btn.click()
                    await page.wait_for_timeout(500)
            except Exception:
                pass

            self._session_warmed = True
            logger.info("[juneyao] session warmed")
        except Exception as exc:
            logger.info("[juneyao] warm-up skipped: %s", exc)

    async def _check_no_flights(self, page: Page) -> bool:
        """检查是否没有航班"""
        try:
            no_flight_text = await page.locator("body").inner_text()
            return "没有查询到符合条件的航班" in no_flight_text
        except Exception:
            return False

    async def _parse_flights(
        self, page: Page, route: Route, flight_date: date
    ) -> List[Dict[str, Any]]:
        """解析航班列表"""
        flights: List[Dict[str, Any]] = []
        seen = set()

        flight_data = await page.evaluate(r'''() => {
            const results = [];
            const bodyText = document.body.innerText;

            // 提取所有航班号（HO 开头）
            const flightNos = bodyText.match(/HO\d{3,4}/g) || [];

            // 提取价格（¥ 后面的数字）
            const prices = [];
            const priceMatches = bodyText.matchAll(/¥(\d{3,5})/g);
            for (const match of priceMatches) {
                prices.push(parseInt(match[1]));
            }

            // 提取时间（格式：HH:MM）
            const times = bodyText.match(/\d{2}:\d{2}/g) || [];

            // 提取机场信息
            const airports = [];
            const airportMatches = bodyText.matchAll(/(宝安T3|虹桥T2|浦东T1|浦东T2|首都T[123]|大兴|白云T[12]|天府T[12]|[\u4e00-\u9fa5]+机场T?\d?)/g);
            for (const match of airportMatches) {
                airports.push(match[1]);
            }

            return {
                flightNos: [...new Set(flightNos)],
                prices: prices,
                times: times,
                airports: airports,
                rawText: bodyText.substring(0, 2000)
            };
        }''')

        flight_nos = flight_data.get("flightNos", [])
        prices = flight_data.get("prices", [])
        times = flight_data.get("times", [])
        airports = flight_data.get("airports", [])

        logger.info(
            "[juneyao] extracted %d flight numbers, %d prices, %d times, %d airports",
            len(flight_nos),
            len(prices),
            len(times),
            len(airports),
        )

        if not flight_nos:
            logger.warning("[juneyao] no flight numbers found in page")
            return []

        # 去重价格
        unique_prices = sorted(set(prices))
        logger.info("[juneyao] unique prices: %s", unique_prices[:10])

        # 为每个航班创建记录
        for i, flight_no in enumerate(flight_nos):
            # 获取对应的价格
            if i < len(unique_prices):
                price = unique_prices[i]
            elif unique_prices:
                price = unique_prices[-1]
            else:
                price = 0

            if price < 100:  # 过滤无效价格
                continue

            # 推断出发和到达机场
            dep_airport = airports[0] if len(airports) > 0 else ""
            arr_airport = airports[1] if len(airports) > 1 else ""

            # 推断起降时间
            dep_time = times[i * 2] if len(times) > i * 2 else ""
            arr_time = times[i * 2 + 1] if len(times) > i * 2 + 1 else ""

            flight = normalize_flight_record(
                route_from=route.from_city,
                route_to=route.to_city,
                flight_date=flight_date,
                flight_no=flight_no,
                airline=JUNEYAO_AIRLINE_NAME,
                price=price,
                source=self.source,
                departure_airport=dep_airport,
                arrival_airport=arr_airport,
                metadata={
                    "record_type": "extracted_from_page",
                    "departure_time": dep_time,
                    "arrival_time": arr_time,
                },
            )

            key = (flight["flight_no"], flight["price"])
            if key not in seen:
                seen.add(key)
                flights.append(flight)

        return flights
