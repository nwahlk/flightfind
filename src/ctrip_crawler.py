"""
Ctrip (携程) 航班爬虫
URL格式: https://flights.ctrip.com/online/list/oneway-{from_code}-{to_code}?depdate={date}
"""

import asyncio
import logging
import random
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from playwright.async_api import ElementHandle, Page, async_playwright

from src.base_crawler import FlightCrawler
from src.config import Route
from src.exceptions import BrowserCrashError, CrawlerError, ParseError
from src.flight_record import normalize_flight_record
from src.utils import retry_with_backoff

logger = logging.getLogger(__name__)


# 携程城市代码映射（IATA 代码）
CTRIP_CITY_CODE_MAP = {
    "北京": "BJS",
    "上海": "SHA",
    "广州": "CAN",
    "深圳": "SZX",
    "成都": "CTU",
    "杭州": "HGH",
    "西安": "XIY",
    "重庆": "CKG",
    "南京": "NKG",
    "武汉": "WUH",
    "天津": "TSN",
    "青岛": "TAO",
    "大连": "DLC",
    "厦门": "XMN",
    "昆明": "KMG",
    "长沙": "CSX",
    "郑州": "CGO",
    "沈阳": "SHE",
    "济南": "TNA",
    "哈尔滨": "HRB",
    "三亚": "SYX",
    "海口": "HAK",
    "福州": "FOC",
    "南宁": "NNG",
}


def get_ctrip_city_code(city_name: str) -> str:
    """获取携程城市代码"""
    return CTRIP_CITY_CODE_MAP.get(city_name, city_name)


def build_ctrip_url(from_city: str, to_city: str, flight_date: date) -> str:
    """构建携程搜索 URL"""
    from_code = get_ctrip_city_code(from_city)
    to_code = get_ctrip_city_code(to_city)
    return f"https://flights.ctrip.com/online/list/oneway-{from_code}-{to_code}?_=1&depdate={flight_date.isoformat()}"


class CtripCrawler(FlightCrawler):
    """携程航班爬虫"""

    source = "ctrip"

    def __init__(self, headless: bool = True, cookie_dir: Path = None):
        super().__init__(
            headless=headless,
            use_stealth=True,
            mobile_mode=False,
            cookie_dir=cookie_dir or Path("data/cookies"),
        )
        self.playwright = None
        self.debug_path = Path("logs")
        self.debug_path.mkdir(parents=True, exist_ok=True)

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def init(self) -> None:
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=self._get_browser_args(),
            )
            options = self._get_context_options()
            self.context = await self.browser.new_context(**options)
            await self._apply_stealth_to_context()
            await self._load_cookies_to_context()
            logger.info("[ctrip] browser initialized")
        except Exception as exc:
            raise BrowserCrashError(f"ctrip browser init failed: {exc}") from exc

    @retry_with_backoff(max_attempts=3, base_delay=4.0)
    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        """搜索航班"""
        results: List[Dict[str, Any]] = []
        for index, flight_date in enumerate(sorted(route.dates.absolute_dates)):
            if index:
                # 携程风控严格，每次查询间隔 30-60 秒
                await self._random_delay(30.0, 60.0)

            try:
                logger.info("[ctrip] searching %s -> %s on %s", route.from_city, route.to_city, flight_date)
                flights = await self._search_single_date(route, flight_date)
                results.extend(flights)
                logger.info("[ctrip] found %d flights for %s -> %s", len(flights), route.from_city, route.to_city)
            except Exception as exc:
                logger.error("[ctrip] search failed for %s -> %s on %s: %s", route.from_city, route.to_city, flight_date, exc)

        return results

    async def _search_single_date(self, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        """搜索单个日期的航班"""
        if not self.context:
            raise CrawlerError("ctrip browser context is not initialized")

        page = await self.context.new_page()

        try:
            url = build_ctrip_url(route.from_city, route.to_city, flight_date)
            logger.info("[ctrip] navigating to: %s", url)

            # 模拟人类操作，增加等待时间
            await self._random_delay(3.0, 5.0)
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # 等待页面完全加载
            await page.wait_for_timeout(random.randint(8000, 12000))

            # 检查是否有风控
            if await self._check_antibot(page):
                raise CrawlerError("ctrip page shows anti-bot detection")

            # 滚动到页面底部，触发懒加载
            await self._scroll_to_bottom(page)

            # 解析航班
            flights = await self._parse_flights(page, route, flight_date)

            # 保存调试信息
            await self._save_debug_snapshot(page, route, flight_date, "page")

            if not flights:
                raise ParseError("ctrip page did not yield any flights")

            return flights

        finally:
            await page.close()

    async def _check_antibot(self, page: Page) -> bool:
        """检查是否有风控"""
        try:
            title = await page.title()
            body = await page.locator("body").inner_text()
            url = page.url

            signals = ["验证", "captcha", "拦截", "禁止访问", "Too Many Requests", "访问频繁"]
            haystack = f"{title}\n{body}\n{url}"
            return any(signal in haystack for signal in signals)
        except Exception:
            return False

    async def _scroll_to_bottom(self, page: Page) -> None:
        """滚动到页面底部，触发懒加载获取全部航班"""
        logger.info("[ctrip] scrolling to bottom to load all flights")

        # 获取页面总高度
        total_height = await page.evaluate("document.body.scrollHeight")
        viewport_height = await page.evaluate("window.innerHeight")

        current_position = 0
        scroll_step = viewport_height // 2  # 每次滚动半个视口高度

        while current_position < total_height:
            # 滚动一步
            current_position += scroll_step
            await page.evaluate(f"window.scrollTo(0, {current_position})")

            # 随机延迟，模拟人类操作
            await page.wait_for_timeout(random.randint(300, 600))

            # 更新页面总高度（可能因为懒加载而增加）
            total_height = await page.evaluate("document.body.scrollHeight")

        # 滚动到底部
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(random.randint(1000, 2000))

        # 滚动回顶部
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(random.randint(500, 1000))

        logger.info("[ctrip] scroll completed")

    async def _parse_flights(self, page: Page, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        """解析航班列表"""
        # 携程航班项选择器
        selectors = [
            ".flight-item.domestic",
            ".flight-item",
            "[class*='flight-item']",
        ]

        items: List[ElementHandle] = []
        for selector in selectors:
            try:
                items = await page.query_selector_all(selector)
                if items:
                    logger.info("[ctrip] found %d flight items via %s", len(items), selector)
                    break
            except Exception:
                continue

        flights: List[Dict[str, Any]] = []
        seen = set()

        for item in items:
            flight = await self._parse_single_flight(item, route, flight_date)
            if not flight:
                continue
            key = (flight["flight_no"], flight["price"])
            if key in seen:
                continue
            seen.add(key)
            flights.append(flight)

        return flights

    async def _parse_single_flight(
        self, item: ElementHandle, route: Route, flight_date: date
    ) -> Dict[str, Any] | None:
        """解析单个航班信息"""
        try:
            text = await item.inner_text()
            if not text or len(text) < 20:
                return None

            # 提取航班号（支持多种格式：2字母+数字、数字+字母+数字等）
            # 格式如: MU1234, 9C7520, CA123, CZ3456
            flight_no_match = re.search(r"\b([A-Z0-9]{2}\d{3,4})\b", text)
            if not flight_no_match:
                return None
            flight_no = flight_no_match.group(1)

            # 提取价格（查找 "数字+起" 格式，如 "510起"）
            price_match = re.search(r"(\d{3,4})\s*起", text)
            if not price_match:
                # 备用：查找 100-9999 之间较小的数字（排除航班号等大数字）
                prices = re.findall(r"(\d{3,4})", text)
                # 过滤掉可能是航班号的数字（> 2000）
                valid_prices = [int(p) for p in prices if 100 <= int(p) <= 2000]
                if not valid_prices:
                    return None
                price = min(valid_prices)
            else:
                price = int(price_match.group(1))

            # 提取时间
            time_match = re.findall(r"\b(\d{2}:\d{2})\b", text)
            dep_time = time_match[0] if time_match else ""
            arr_time = time_match[1] if len(time_match) > 1 else ""

            # 提取机场信息（格式如: 宝安国际机场T3, 虹桥国际机场T1）
            airport_pattern = r"([\u4e00-\u9fa5]+国际机场T?\d?|[\u4e00-\u9fa5]+机场T?\d?)"
            airports = re.findall(airport_pattern, text)
            dep_airport = airports[0] if airports else ""
            arr_airport = airports[1] if len(airports) > 1 else ""

            # 推断航空公司
            airline = self._guess_airline(flight_no)

            return normalize_flight_record(
                route_from=route.from_city,
                route_to=route.to_city,
                flight_date=flight_date,
                flight_no=flight_no,
                airline=airline,
                price=price,
                source=self.source,
                departure_airport=dep_airport,
                arrival_airport=arr_airport,
                metadata={
                    "record_type": "flight_list_page",
                    "departure_time": dep_time,
                    "arrival_time": arr_time,
                },
            )
        except Exception as e:
            logger.debug("[ctrip] failed to parse flight item: %s", e)
            return None

    def _guess_airline(self, flight_no: str) -> str:
        """根据航班号推断航空公司"""
        prefix = flight_no[:2].upper()
        airline_map = {
            "MU": "东方航空",
            "CA": "中国国航",
            "CZ": "南方航空",
            "HU": "海南航空",
            "ZH": "深圳航空",
            "FM": "上海航空",
            "MF": "厦门航空",
            "SC": "山东航空",
            "3U": "四川航空",
            "HO": "吉祥航空",
            "9C": "春秋航空",
            "GS": "天津航空",
            "PN": "西部航空",
            "G5": "华夏航空",
            "JR": "吉祥航空",
            "EU": "成都航空",
            "AQ": "九元航空",
            "RY": "江西航空",
            "GT": "桂林航空",
            "GX": "北部湾航空",
            "DR": "瑞丽航空",
            "QW": "青岛航空",
            "A6": "红土航空",
            "Y8": "扬子江航空",
            "DZ": "东海航空",
            "OQ": "重庆航空",
            "CN": "大新华航空",
            "KN": "中国联航",
            "NS": "河北航空",
            "JD": "首都航空",
            "GJ": "长龙航空",
            "FU": "福州航空",
            "TV": "西藏航空",
            "UQ": "乌鲁木齐航空",
            "RY": "江西航空",
        }
        return airline_map.get(prefix, prefix)

    async def _save_debug_snapshot(
        self, page: Page, route: Route, flight_date: date, suffix: str
    ) -> None:
        """保存调试快照"""
        safe_name = f"ctrip_{route.from_city}_{route.to_city}_{flight_date.isoformat()}_{suffix}"
        html_path = self.debug_path / f"{safe_name}.html"
        png_path = self.debug_path / f"{safe_name}.png"

        try:
            html_path.write_text(await page.content(), encoding="utf-8")
        except Exception:
            pass

        try:
            await page.screenshot(path=str(png_path), full_page=True)
        except Exception:
            pass

    async def close(self) -> None:
        """关闭浏览器资源"""
        await self._save_cookies_from_context()
        if self.context:
            await self.context.close()
            self.context = None
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
