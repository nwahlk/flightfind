"""
China Eastern Airlines (东方航空) official-site crawler.
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

from playwright.async_api import ElementHandle, Page, async_playwright

from src.base_crawler import FlightCrawler
from src.config import Route
from src.exceptions import BrowserCrashError, CrawlerError, ParseError
from src.flight_record import normalize_flight_record
from src.utils import retry_with_backoff

logger = logging.getLogger(__name__)


# 东航城市代码映射
MU_CITY_CODE_MAP = {
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

MU_AIRLINE_NAME = "东方航空"
MU_HOMEPAGE_URL = "https://www.ceair.com/"


def get_mu_city_code(city_name: str) -> str:
    """获取东航城市代码"""
    return MU_CITY_CODE_MAP.get(city_name, city_name)


class MuCrawler(FlightCrawler):
    """东方航空爬虫"""

    source = "mu"

    def __init__(self, headless: bool = True):
        super().__init__(headless=headless)
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
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            self.context = await self.browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                extra_http_headers={
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Referer": "https://www.ceair.com/",
                },
            )
            await self.context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
        except Exception as exc:
            raise BrowserCrashError(f"mu browser init failed: {exc}") from exc

    @retry_with_backoff(max_attempts=3, base_delay=4.0)
    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        """搜索航班"""
        results: List[Dict[str, Any]] = []
        for index, flight_date in enumerate(sorted(route.dates.absolute_dates)):
            if index:
                await self._random_delay(8.0, 14.0)
            try:
                flights = await self._search_single_date(route, flight_date)
                results.extend(flights)
            except Exception as exc:
                logger.error(
                    "[mu] search failed for %s -> %s on %s: %s",
                    route.from_city, route.to_city, flight_date, exc
                )
        return results

    async def _search_single_date(
        self, route: Route, flight_date: date
    ) -> List[Dict[str, Any]]:
        """搜索单个日期的航班"""
        if not self.context:
            raise CrawlerError("mu browser context is not initialized")

        await self._warm_session()
        page = await self.context.new_page()

        try:
            url = self._build_search_url(route, flight_date)
            await self._random_delay(1.5, 3.0)
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(random.randint(5000, 8000))

            # 检查是否有反爬
            if await self._check_antibot(page):
                raise CrawlerError("mu page shows anti-bot detection")

            flights = await self._parse_flights(page, route, flight_date)
            await self._save_debug_snapshot(page, route, flight_date, "page")

            if not flights:
                raise ParseError("mu page did not yield any flights")

            return flights
        finally:
            await page.close()

    def _build_search_url(self, route: Route, flight_date: date) -> str:
        """构建搜索 URL"""
        from_code = get_mu_city_code(route.from_city)
        to_code = get_mu_city_code(route.to_city)
        # 东航搜索 URL 格式
        return f"https://www.ceair.com/booking/{from_code}-{to_code}-{flight_date.strftime('%Y%m%d')}/"

    async def _warm_session(self) -> None:
        """预热会话"""
        if self._session_warmed or not self.context:
            return

        page = await self.context.new_page()
        try:
            await page.goto(MU_HOMEPAGE_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(random.randint(3000, 5000))
            self._session_warmed = True
        except Exception as exc:
            logger.info("[mu] warm-up page skipped: %s", exc)
        finally:
            await page.close()

    async def _check_antibot(self, page: Page) -> bool:
        """检查是否有反爬检测"""
        try:
            title = await page.title()
            body = await page.locator("body").inner_text()
            signals = ["验证", "captcha", "拦截", "禁止访问", "Too Many Requests"]
            haystack = f"{title}\n{body}"
            return any(signal in haystack for signal in signals)
        except Exception:
            return False

    async def _parse_flights(
        self, page: Page, route: Route, flight_date: date
    ) -> List[Dict[str, Any]]:
        """解析航班列表"""
        # 东航页面的航班项选择器（需要根据实际页面调整）
        selectors = [
            ".flight-item",
            "[class*='flight']",
            ".flight-list li",
        ]

        items: List[ElementHandle] = []
        for selector in selectors:
            try:
                items = await page.query_selector_all(selector)
                if items:
                    logger.info("[mu] found %s flight items via %s", len(items), selector)
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
            if not text or len(text) < 10:
                return None

            # 提取航班号（MU开头）
            flight_match = re.search(r"\b(MU\d{3,4})\b", text, re.IGNORECASE)
            if not flight_match:
                return None
            flight_no = flight_match.group(1).upper()

            # 提取价格
            price_match = re.search(r"[¥￥]?\s*(\d{2,5})", text)
            if not price_match:
                return None
            price = int(price_match.group(1))
            if price < 10:
                return None

            return normalize_flight_record(
                route_from=route.from_city,
                route_to=route.to_city,
                flight_date=flight_date,
                flight_no=flight_no,
                airline=MU_AIRLINE_NAME,
                price=price,
                source=self.source,
                metadata={"record_type": "flight_list_page"},
            )
        except Exception:
            return None

    async def _save_debug_snapshot(
        self, page: Page, route: Route, flight_date: date, suffix: str
    ) -> None:
        """保存调试快照"""
        safe_name = f"mu_{route.from_city}_{route.to_city}_{flight_date.isoformat()}_{suffix}"
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
        if self.context:
            await self.context.close()
            self.context = None
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
