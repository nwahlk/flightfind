"""
深圳航空 (Shenzhen Airlines) 官网爬虫
移动端URL: https://m.shenzhenair.com/webresource-micro/queryFlights.html
"""

import asyncio
import json
import logging
import random
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlencode

from playwright.async_api import Page, async_playwright

from src.base_crawler import FlightCrawler
from src.city_codes import COMMON_CITY_CODE_MAP
from src.config import Route
from src.exceptions import BrowserCrashError, CrawlerError, ParseError
from src.flight_record import normalize_flight_record
from src.utils import retry_with_backoff

logger = logging.getLogger(__name__)


# 深圳航空城市代码映射（使用共享映射）
SHENZHEN_CITY_CODE_MAP = COMMON_CITY_CODE_MAP

SHENZHEN_AIRLINE_NAME = "深圳航空"

# 深圳航空城市名称映射（页面中显示的是"上海虹桥"、"上海浦东"等）
SHENZHEN_CITY_NAME_MAP = {
    "北京": "北京首都",
    "上海": "上海虹桥",  # 默认使用虹桥
    "广州": "广州",
    "深圳": "深圳",
    "成都": "成都天府",
    "杭州": "杭州",
    "西安": "西安",
    "重庆": "重庆",
    "南京": "南京",
    "武汉": "武汉",
    "天津": "天津",
    "青岛": "青岛",
    "大连": "大连",
    "厦门": "厦门",
    "昆明": "昆明",
    "长沙": "长沙",
    "郑州": "郑州",
    "沈阳": "沈阳",
    "济南": "济南",
    "哈尔滨": "哈尔滨",
    "三亚": "三亚",
    "海口": "海口",
    "福州": "福州",
    "南宁": "南宁",
    "贵阳": "贵阳",
    "长春": "长春",
    "太原": "太原",
    "兰州": "兰州",
    "乌鲁木齐": "乌鲁木齐",
    "呼和浩特": "呼和浩特",
    "银川": "银川",
    "西宁": "西宁",
    "拉萨": "拉萨",
    "合肥": "合肥",
    "南昌": "南昌",
    "石家庄": "石家庄",
    "温州": "温州",
    "宁波": "宁波",
    "无锡": "无锡",
    "烟台": "烟台",
    "珠海": "珠海",
    "惠州": "惠州",
}


def get_shenzhen_city_code(city_name: str) -> str:
    """获取深圳航空城市代码"""
    return SHENZHEN_CITY_CODE_MAP.get(city_name, city_name)


class ShenzhenCrawler(FlightCrawler):
    """深圳航空航班爬虫"""

    source = "shenzhen"

    def __init__(self, headless: bool = True, cookie_dir: Path = None):
        super().__init__(
            headless=headless,
            use_stealth=True,
            mobile_mode=True,
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
            logger.info("[shenzhen] browser initialized")
        except Exception as exc:
            raise BrowserCrashError(f"shenzhen browser init failed: {exc}") from exc

    @retry_with_backoff(max_attempts=3, base_delay=4.0)
    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        """搜索航班"""
        results: List[Dict[str, Any]] = []

        for index, flight_date in enumerate(sorted(route.dates.absolute_dates)):
            if index:
                await self._random_delay(10.0, 20.0)

            try:
                logger.info(
                    "[shenzhen] searching %s -> %s on %s",
                    route.from_city,
                    route.to_city,
                    flight_date,
                )
                flights = await self._search_single_date(route, flight_date)
                results.extend(flights)
                logger.info(
                    "[shenzhen] found %d flights for %s -> %s",
                    len(flights),
                    route.from_city,
                    route.to_city,
                )
            except Exception as exc:
                logger.error(
                    "[shenzhen] search failed for %s -> %s on %s: %s",
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
            raise CrawlerError("shenzhen browser context is not initialized")

        page = await self.context.new_page()

        try:
            # 深圳航空移动端航班查询页面
            await self._warm_session(page)
            await self._random_delay(2.0, 3.0)

            # 先加载查询页面
            url = "https://m.shenzhenair.com/webresource-micro/queryFlights.html?v=0.45"
            logger.info("[shenzhen] navigating to: %s", url)
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(random.randint(3000, 5000))

            # 使用 JavaScript 设置城市和日期，然后触发查询
            from_city_display = self._get_display_city_name(route.from_city)
            to_city_display = self._get_display_city_name(route.to_city)
            date_str = flight_date.strftime("%Y-%m-%d")

            # 执行 JavaScript 来设置城市和日期，然后点击查询
            await page.evaluate(f'''() => {{
                // 设置出发城市
                const orgCityEl = document.getElementById('booksOrgCityName');
                if (orgCityEl) orgCityEl.innerText = '{from_city_display}';

                // 设置到达城市
                const dstCityEl = document.getElementById('booksDstCityName');
                if (dstCityEl) dstCityEl.innerText = '{to_city_display}';

                // 设置日期
                const dateEl = document.getElementById('booksQueryFlightOrgDateEL');
                if (dateEl) dateEl.value = '{date_str}';

                const dateShowEl = document.getElementById('booksQueryFlightOrgDate');
                if (dateShowEl) dateShowEl.innerText = '{date_str}';

                console.log('Set cities: {from_city_display} -> {to_city_display}, date: {date_str}');
            }}''')
            await page.wait_for_timeout(1000)

            # 点击查询按钮
            search_btn = await page.query_selector('#popup-submit')
            if search_btn:
                await search_btn.click()
                logger.info("[shenzhen] clicked search button")
            else:
                logger.warning("[shenzhen] search button not found")

            # 等待页面加载
            await page.wait_for_timeout(random.randint(10000, 15000))

            # 保存调试快照
            await self._save_debug_snapshot(page, route, flight_date, "result_page")

            # 解析航班
            flights = await self._parse_flights(page, route, flight_date)

            if not flights:
                logger.warning("[shenzhen] no flights found for %s", flight_date)
                return []

            return flights

        except Exception as exc:
            await self._save_debug_snapshot(page, route, flight_date, "error")
            raise CrawlerError(f"shenzhen search failed: {exc}") from exc
        finally:
            await page.close()

    async def _warm_session(self, page: Page) -> None:
        """预热 session"""
        if self._session_warmed:
            return

        try:
            await page.goto(
                "https://m.shenzhenair.com/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await page.wait_for_timeout(random.randint(2000, 3000))
            self._session_warmed = True
            logger.info("[shenzhen] session warmed")
        except Exception as exc:
            logger.info("[shenzhen] warm-up skipped: %s", exc)

    def _get_display_city_name(self, input_city: str) -> str:
        """获取页面显示的城市名称"""
        return SHENZHEN_CITY_NAME_MAP.get(input_city, input_city)

    async def _select_city(
        self, page: Page, city_name: str, is_departure: bool
    ) -> None:
        """选择城市"""
        try:
            # 获取页面显示的城市名称
            display_city = self._get_display_city_name(city_name)

            # 直接使用 JavaScript 设置城市值
            element_id = "booksOrgCityName" if is_departure else "booksDstCityName"
            await page.evaluate(f'''() => {{
                // 查找城市数据
                const cityItems = document.querySelectorAll('.cityUl li[data-tags]');
                let targetItem = null;
                for (const item of cityItems) {{
                    if (item.getAttribute('data-tags') === '{display_city}') {{
                        targetItem = item;
                        break;
                    }}
                }}

                if (targetItem) {{
                    // 设置城市名称
                    document.getElementById('{element_id}').innerText = '{display_city}';

                    // 设置城市代码
                    const cityCode = targetItem.getAttribute('data-value');
                    if ('{element_id}' === 'booksOrgCityName') {{
                        window.booksOrgCity = cityCode;
                    }} else {{
                        window.booksDstCity = cityCode;
                    }}

                    console.log('Set city: {display_city}, code: ' + cityCode);
                }} else {{
                    console.log('City not found: {display_city}');
                }}
            }}''')
            await page.wait_for_timeout(500)
            logger.info("[shenzhen] set city: %s", display_city)

        except Exception as exc:
            logger.warning("[shenzhen] failed to select city %s: %s", city_name, exc)

    async def _select_date(self, page: Page, flight_date: date) -> None:
        """选择日期"""
        try:
            # 点击日期区域
            date_cell = await page.query_selector("heading >> cell")
            if date_cell:
                await date_cell.click()
                await page.wait_for_timeout(500)

            # 在日历中选择日期
            day = flight_date.day
            date_item = await page.query_selector(f'text="{day}"')
            if date_item:
                await date_item.click()
                await page.wait_for_timeout(300)

        except Exception as exc:
            logger.warning("[shenzhen] failed to select date %s: %s", flight_date, exc)

    async def _parse_flights(
        self, page: Page, route: Route, flight_date: date
    ) -> List[Dict[str, Any]]:
        """解析航班列表"""
        flights: List[Dict[str, Any]] = []
        seen = set()

        flight_data = await page.evaluate(r'''() => {
            const results = [];
            const bodyText = document.body.innerText;

            // 提取所有航班号（ZH 开头）
            const flightNos = bodyText.match(/ZH\d{3,4}/g) || [];

            // 提取价格（¥ 后面的数字）
            const prices = [];
            const priceMatches = bodyText.matchAll(/¥\s*(\d{3,5})/g);
            for (const match of priceMatches) {
                prices.push(parseInt(match[1]));
            }

            // 提取时间（格式：HH:MM）
            const times = bodyText.match(/\d{2}:\d{2}/g) || [];

            return {
                flightNos: [...new Set(flightNos)],
                prices: prices,
                times: times,
            };
        }''')

        flight_nos = flight_data.get("flightNos", [])
        prices = flight_data.get("prices", [])
        times = flight_data.get("times", [])

        logger.info(
            "[shenzhen] extracted %d flight numbers, %d prices",
            len(flight_nos),
            len(prices),
        )

        if not flight_nos:
            logger.warning("[shenzhen] no flight numbers found in page")
            return []

        # 去重价格
        unique_prices = sorted(set(prices))

        # 为每个航班创建记录
        for i, flight_no in enumerate(flight_nos):
            if i < len(unique_prices):
                price = unique_prices[i]
            elif unique_prices:
                price = unique_prices[-1]
            else:
                continue

            if price < 100:
                continue

            flight = normalize_flight_record(
                route_from=route.from_city,
                route_to=route.to_city,
                flight_date=flight_date,
                flight_no=flight_no,
                airline=SHENZHEN_AIRLINE_NAME,
                price=price,
                source=self.source,
                departure_airport="",
                arrival_airport="",
                metadata={
                    "record_type": "extracted_from_page",
                },
            )

            key = (flight["flight_no"], flight["price"])
            if key not in seen:
                seen.add(key)
                flights.append(flight)

        return flights
