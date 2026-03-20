"""
Ctrip crawler.
"""

import asyncio
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import Browser, BrowserContext, ElementHandle, Page, async_playwright

from src.base_crawler import FlightCrawler
from src.config import Route
from src.exceptions import (
    AntiBotError,
    BrowserCrashError,
    CrawlerError,
    NetworkError,
    ParseError,
    TimeoutError,
)
from src.flight_record import normalize_flight_record
from src.utils import retry_with_backoff

logger = logging.getLogger(__name__)


KNOWN_AIRLINES = {
    "MU",
    "CA",
    "CZ",
    "3U",
    "ZH",
    "HO",
    "FM",
    "9C",
    "KN",
    "JD",
    "NS",
    "8L",
    "OQ",
    "TV",
    "GS",
    "EU",
    "DR",
    "QW",
    "GT",
    "UQ",
    "GX",
    "RY",
    "YI",
    "DZ",
    "KY",
}


CITY_CODE_MAP = {
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


def get_city_code(city_name: str) -> str:
    return CITY_CODE_MAP.get(city_name, city_name)


class CtripCrawler(FlightCrawler):
    source = "ctrip"

    def __init__(
        self,
        headless: bool = True,
        debug_save_html: bool = False,
        debug_html_path: Optional[Path] = None,
        page_load_timeout: int = 45000,
    ):
        super().__init__(headless=headless)
        self.debug_save_html = debug_save_html
        self.debug_html_path = debug_html_path or Path("./logs")
        self.page_load_timeout = page_load_timeout
        self.playwright = None
        if self.debug_save_html:
            self.debug_html_path.mkdir(parents=True, exist_ok=True)

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def init(self) -> None:
        try:
            self.playwright = await async_playwright().start()
            launch_kwargs = {
                "headless": self.headless,
                "args": [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--disable-blink-features=AutomationControlled",
                ],
                "slow_mo": 100,
            }
            chrome_exe = self._find_local_chrome()
            if chrome_exe and chrome_exe.exists():
                launch_kwargs["executable_path"] = str(chrome_exe)

            self.browser: Browser = await self.playwright.chromium.launch(**launch_kwargs)
            self.context: BrowserContext = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                ignore_https_errors=True,
                java_script_enabled=True,
            )
            await self.context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
                window.chrome = { runtime: {} };
                """
            )
        except Exception as e:
            raise BrowserCrashError(f"browser init failed: {e}")

    def _find_local_chrome(self) -> Optional[Path]:
        home = Path.home()
        paths = []
        paths.extend(home.glob("AppData/Local/ms-playwright/chromium-*/chrome-win64/chrome.exe"))
        paths.extend(home.glob(".cache/ms-playwright/chromium-*/chrome-linux/chrome"))
        paths.extend(
            home.glob("Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium")
        )
        paths = [p for p in paths if p.exists()]
        if not paths:
            return None
        paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return paths[0]

    @retry_with_backoff(max_attempts=3, base_delay=5.0)
    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        if not self.page:
            self.page = await self.context.new_page()

        results: List[Dict[str, Any]] = []
        for flight_date in route.dates.absolute_dates:
            try:
                results.extend(await self._search_single_date(route, flight_date))
            except Exception as e:
                logger.error(f"search failed for {flight_date}: {e}")
                raise CrawlerError(f"search failed for {flight_date}: {e}")
        return results

    async def _search_single_date(self, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        date_str = flight_date.strftime("%Y-%m-%d")
        url = self._build_search_url(route.from_city, route.to_city, date_str)
        try:
            response = await self.page.goto(url, wait_until="networkidle", timeout=self.page_load_timeout)
            if not response or response.status != 200:
                raise NetworkError(f"page load failed: HTTP {response.status if response else 'None'}")

            await self._dismiss_popups()
            if await self._detect_anti_bot():
                raise AntiBotError("anti-bot verification detected")

            try:
                await self.page.wait_for_selector(".flight-box, .flight-item", timeout=30000)
            except Exception:
                logger.warning("flight list selector not found, continue parsing anyway")

            await asyncio.sleep(1)

            if self.debug_save_html:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"ctrip_debug_{route.from_city}_{route.to_city}_{date_str}_{timestamp}.html"
                debug_file = self.debug_html_path / filename
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(await self.page.content())

            return await self._parse_flights(route, flight_date)
        except Exception as e:
            if isinstance(e, (AntiBotError, NetworkError, TimeoutError)):
                raise
            raise ParseError(f"parse failed: {e}")

    async def _dismiss_popups(self) -> None:
        close_selectors = [
            ".next-dialog-close",
            ".dialog-close",
            ".close-btn",
            ".btn-close",
            ".J_Close",
            "[class*='close']",
            "[aria-label='关闭']",
            "[aria-label='Close']",
        ]
        for selector in close_selectors:
            try:
                locator = self.page.locator(selector).first
                if await locator.count() and await locator.is_visible():
                    await locator.click(timeout=1000)
                    await asyncio.sleep(0.2)
            except Exception:
                continue

        for text in ["Close", "I know", "OK", "Accept", "Confirm"]:
            try:
                locator = self.page.get_by_text(text).first
                if await locator.count() and await locator.is_visible():
                    await locator.click(timeout=800)
                    await asyncio.sleep(0.2)
            except Exception:
                continue

    def _build_search_url(self, from_city: str, to_city: str, date_str: str) -> str:
        from_code = get_city_code(from_city)
        to_code = get_city_code(to_city)
        return (
            "https://flights.ctrip.com/itinerary/oneway/"
            f"{from_code}-{to_code}?depdate={date_str}&adult=1&child=0&infant=0"
        )

    async def _detect_anti_bot(self) -> bool:
        selectors = [".captcha", "#captcha", ".slider", ".verify-code", "[class*='anti']"]
        for selector in selectors:
            try:
                element = await self.page.query_selector(selector)
                if element and await element.is_visible():
                    return True
            except Exception:
                continue

        try:
            text = await self.page.inner_text("body")
            keywords = ["captcha", "verify", "security check", "slider"]
            return any(k in text for k in keywords)
        except Exception:
            return False

    async def _parse_flights(self, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        selectors = [".flight-box", ".flight-item", "[class*='flightItem']"]
        items: List[ElementHandle] = []
        for selector in selectors:
            items = await self.page.query_selector_all(selector)
            if items:
                break

        flights: List[Dict[str, Any]] = []
        for item in items:
            flight = await self._parse_single_flight(item, route, flight_date)
            if flight:
                flights.append(flight)
        return flights

    async def _parse_single_flight(
        self, item: ElementHandle, route: Route, flight_date: date
    ) -> Optional[Dict[str, Any]]:
        try:
            raw = (await item.inner_text()).strip()
            if not raw:
                return None

            flight_no_raw = await self._get_text(
                item, [".plane-No", ".flight-no", ".flight-number", "[class*='plane-No']"]
            )
            flight_no = "Unknown"
            if flight_no_raw:
                m = re.search(r"([A-Z]{2,3}\d{3,4})", flight_no_raw.strip())
                if m:
                    candidate = m.group(1)
                    if candidate[:2] in KNOWN_AIRLINES:
                        flight_no = candidate

            airline = await self._get_text(
                item, [".airline-name", ".airline", ".company-name", "[class*='airline']"]
            )
            if not airline:
                m = re.search(r"([\u4e00-\u9fa5]{2,}(航空|航司|航空公司))", raw)
                airline = m.group(1) if m else "Unknown"

            price_text = await self._get_text(
                item, [".low-price-flights-route-flight-price", ".price", ".amount", "[class*='price']"]
            )
            if not price_text:
                price_text = raw
            price_match = re.search(r"(?:¥|￥)?\s*(\d{2,5})", price_text)
            if not price_match:
                return None
            price = int(price_match.group(1))
            if price < 10:
                return None

            departure_airport = await self._get_text(
                item, [".flight-port", "[data-flight-port]", ".departure-airport", "[data-departure-port]"]
            )
            arrival_airport = await self._get_text(
                item, [".arrival-port", "[data-arrival-port]", ".destination-airport"]
            )

            return normalize_flight_record(
                route_from=route.from_city,
                route_to=route.to_city,
                flight_date=flight_date,
                flight_no=flight_no,
                airline=airline,
                price=price,
                source=self.source,
                departure_airport=departure_airport,
                arrival_airport=arrival_airport,
            )
        except Exception:
            return None

    async def _get_text(self, item: ElementHandle, selectors: List[str]) -> str:
        for selector in selectors:
            try:
                elem = await item.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if text:
                        return text.strip()
            except Exception:
                continue
        return ""

    async def close(self) -> None:
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass

