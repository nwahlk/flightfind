"""Spring Airlines official-site crawler."""

import asyncio
import json
import logging
import random
import re
import time
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
from src.utils import (
    DOM_TEXT_WALKER_JS,
    clean_dom_texts,
    extract_airports,
    extract_price_forward,
    extract_times,
    retry_with_backoff,
)

logger = logging.getLogger(__name__)

SPRING_CITY_CODE_MAP = COMMON_CITY_CODE_MAP
SPRING_AIRLINE_NAME = "春秋航空"


def get_spring_city_code(city_name: str) -> str:
    return SPRING_CITY_CODE_MAP.get(city_name, city_name)


class SpringCrawler(FlightCrawler):
    source = "spring"

    def __init__(self, headless: bool = True):
        super().__init__(headless=headless)
        self.playwright = None
        self.debug_path = Path("logs")
        self.debug_path.mkdir(parents=True, exist_ok=True)
        self._session_warmed = False
        self._list_cooldown_until = 0.0

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def init(self) -> None:
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
                    "Referer": "https://flights.ch.com/",
                },
            )
            await self.context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
        except Exception as exc:
            raise BrowserCrashError(f"spring browser init failed: {exc}") from exc

    @retry_with_backoff(max_attempts=3, base_delay=4.0)
    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for index, flight_date in enumerate(sorted(route.dates.resolved_dates())):
            if index:
                await self._human_pause(30.0, 60.0)
            try:
                if self._should_skip_list_page():
                    logger.info(
                        "[spring] list page is cooling down, use calendar fallback for %s %s -> %s",
                        flight_date,
                        route.from_city,
                        route.to_city,
                    )
                    results.extend(await self._search_calendar_fallback(route, flight_date))
                    continue

                list_results = await self._search_single_date(route, flight_date)
                results.extend(list_results)
            except Exception as exc:
                logger.warning(
                    "[spring] list page failed for %s %s -> %s, fallback to calendar: %s",
                    flight_date,
                    route.from_city,
                    route.to_city,
                    exc,
                )
                results.extend(await self._search_calendar_fallback(route, flight_date))
        return results

    async def _search_single_date(
        self,
        route: Route,
        flight_date: date,
    ) -> List[Dict[str, Any]]:
        if not self.context:
            raise CrawlerError("spring browser context is not initialized")

        await self._warm_session()
        page = await self.context.new_page()
        url = self._build_list_url(route.from_city, route.to_city, flight_date)

        try:
            await self._human_pause(1.5, 3.5)
            response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(random.randint(10000, 14000))
            if response and response.status in (403, 429):
                if response.status == 429:
                    self._activate_list_cooldown()
                raise CrawlerError(f"spring list page returned HTTP {response.status}")
            if await self._is_rate_limited(page):
                self._activate_list_cooldown()
                raise CrawlerError("spring list page was rate limited")
        except Exception as exc:
            await self._save_debug_snapshot(page, route, flight_date, "list_error")
            await page.close()
            raise CrawlerError(f"spring list page load failed: {exc}") from exc

        flights = await self._parse_list_page(page, route, flight_date)
        await self._save_debug_snapshot(page, route, flight_date, "list_page")
        await page.close()
        if not flights:
            raise ParseError("spring list page did not yield any flights")
        return flights

    async def _search_calendar_fallback(self, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        if not self.context:
            raise CrawlerError("spring browser context is not initialized")

        page = await self.context.new_page()
        collected: List[Dict[str, Any]] = []
        response_tasks: List[asyncio.Task] = []

        async def capture_response(response) -> None:
            if "Flights/MinPriceTrends" not in response.url or response.status != 200:
                return
            try:
                payload = json.loads(await response.text())
            except Exception:
                return
            trends = payload.get("PriceTrends") or []
            if payload.get("Code") == "0" and trends:
                collected.append(payload)

        page.on(
            "response",
            lambda response: response_tasks.append(asyncio.create_task(capture_response(response))),
        )

        url = self._build_calendar_url(route.from_city, route.to_city, flight_date)

        try:
            await self._human_pause(2.0, 4.0)
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(random.randint(8000, 11000))
            if response_tasks:
                await asyncio.gather(*response_tasks, return_exceptions=True)
        except Exception as exc:
            await self._save_debug_snapshot(page, route, flight_date, "calendar_error")
            await page.close()
            raise CrawlerError(f"spring calendar page load failed: {exc}") from exc

        await self._save_debug_snapshot(page, route, flight_date, "calendar_page")
        await page.close()

        price_by_date: Dict[str, int] = {}
        for payload in collected:
            for item in payload.get("PriceTrends", []):
                flight_date_str = item.get("Date")
                price = item.get("Price")
                if not flight_date_str or price is None:
                    continue
                previous = price_by_date.get(flight_date_str)
                current = int(price)
                price_by_date[flight_date_str] = current if previous is None else min(previous, current)

        if not price_by_date:
            raise ParseError("spring returned no usable price trend data")

        results: List[Dict[str, Any]] = []
        key = flight_date.isoformat()
        if key in price_by_date:
            results.append(
                normalize_flight_record(
                    route_from=route.from_city,
                    route_to=route.to_city,
                    flight_date=flight_date,
                    flight_no="",
                    airline=SPRING_AIRLINE_NAME,
                    price=price_by_date[key],
                    source=self.source,
                    metadata={"record_type": "daily_min_price_calendar"},
                    allow_empty_flight_no=True,
                )
            )
        return results

    def _build_list_url(self, from_city: str, to_city: str, flight_date: date) -> str:
        from_code = get_spring_city_code(from_city)
        to_code = get_spring_city_code(to_city)
        query = urlencode(
            {
                "Departure": from_city,
                "Arrival": to_city,
                "FDate": flight_date.isoformat(),
                "DepartCityCode": from_code,
                "ArriveCityCode": to_code,
            }
        )
        return f"https://flights.ch.com/{from_code}-{to_code}.html?{query}"

    def _build_calendar_url(self, from_city: str, to_city: str, flight_date: date) -> str:
        from_code = get_spring_city_code(from_city)
        to_code = get_spring_city_code(to_city)
        return f"https://flights.ch.com/{from_code}-{to_code}/?FDate={flight_date.isoformat()}"

    async def _human_pause(self, min_seconds: float, max_seconds: float) -> None:
        await asyncio.sleep(random.uniform(min_seconds, max_seconds))

    async def _warm_session(self) -> None:
        if self._session_warmed or not self.context:
            return

        page = await self.context.new_page()
        try:
            await page.goto("https://flights.ch.com/", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(random.randint(3000, 6000))
            self._session_warmed = True
        except Exception as exc:
            logger.info("[spring] warm-up page skipped: %s", exc)
        finally:
            await page.close()

    def _activate_list_cooldown(self, cooldown_seconds: int = 1800) -> None:
        self._list_cooldown_until = time.monotonic() + cooldown_seconds

    def _should_skip_list_page(self) -> bool:
        return time.monotonic() < self._list_cooldown_until

    async def _is_rate_limited(self, page: Page) -> bool:
        try:
            title = await page.title()
            body = await page.locator("body").inner_text()
        except Exception:
            return False
        signals = ["Too Many Requests", "429", "访问过于频繁", "请求过于频繁"]
        haystack = f"{title}\n{body}"
        return any(signal in haystack for signal in signals)

    async def _parse_list_page(self, page: Page, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        flights = await self._parse_list_page_from_dom(page, route, flight_date)
        if flights:
            return flights

        logger.info("[spring] DOM parsing yielded no results, falling back to CSS selectors")
        selectors = [
            ".flight-item-new",
            ".flight-list .flight-item-new",
            ".flight-list.zh-cn .flight-item-new",
            ".flight-list-item",
            ".journey-item",
            ".flight-item",
            ".flight-row",
            "[class*='flight-item']",
            "[class*='journey-item']",
            "[class*='list-item']",
        ]
        items: List[ElementHandle] = []
        for selector in selectors:
            try:
                items = await page.query_selector_all(selector)
            except Exception:
                items = []
            if items:
                logger.info("[spring] found %s candidate nodes via %s", len(items), selector)
                break

        flights: List[Dict[str, Any]] = []
        seen = set()
        for item in items:
            flight = await self._parse_single_list_item(item, route, flight_date)
            if not flight:
                continue
            dedupe_key = (flight["flight_no"], flight["price"], flight["route_from"], flight["route_to"])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            flights.append(flight)
        return flights

    async def _parse_list_page_from_dom(self, page: Page, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        try:
            flight_blocks = await page.evaluate(DOM_TEXT_WALKER_JS, "订票")
        except Exception as exc:
            logger.warning("[spring] DOM text extraction failed: %s", exc)
            return []

        if not flight_blocks:
            return []

        logger.info("[spring] found %d flight blocks from DOM", len(flight_blocks))

        flights: List[Dict[str, Any]] = []
        seen = set()

        for block in flight_blocks:
            flight = self._parse_spring_dom_block(block, route, flight_date)
            if not flight:
                continue
            key = (flight["flight_no"], flight["price"])
            if key not in seen:
                seen.add(key)
                flights.append(flight)

        logger.info("[spring] parsed %d flights from DOM", len(flights))
        return flights

    def _parse_spring_dom_block(self, block: List[str], route: Route, flight_date: date) -> Dict[str, Any] | None:
        cleaned = clean_dom_texts(block)

        flight_no = ""
        flight_no_idx = -1
        for index, text in enumerate(cleaned):
            match = re.search(r"\b(9C\d{3,4})\b", text)
            if match:
                flight_no = match.group(1)
                flight_no_idx = index
                break

        if not flight_no:
            return None

        remaining = cleaned[flight_no_idx + 1:]
        dep_time, arr_time = extract_times(remaining)
        dep_airport, arr_airport = extract_airports(remaining)
        price = extract_price_forward(remaining)

        if price <= 0:
            return None

        return normalize_flight_record(
            route_from=route.from_city,
            route_to=route.to_city,
            flight_date=flight_date,
            flight_no=flight_no,
            airline=SPRING_AIRLINE_NAME,
            price=price,
            source=self.source,
            departure_airport=dep_airport,
            arrival_airport=arr_airport,
            metadata={
                "record_type": "dom_text_block",
                "departure_time": dep_time,
                "arrival_time": arr_time,
            },
            allow_empty_flight_no=True,
        )

    async def _parse_single_list_item(
        self,
        item: ElementHandle,
        route: Route,
        flight_date: date,
    ) -> Dict[str, Any] | None:
        try:
            raw_text = (await item.inner_text()).strip()
            if not raw_text:
                return None

            flight_no = (await item.get_attribute("data-shizhu-flightno") or "").strip().upper()
            if not flight_no:
                flight_match = re.search(r"\b([A-Z0-9]{2,3}\d{3,4})\b", raw_text)
                flight_no = flight_match.group(1) if flight_match else ""

            airline = SPRING_AIRLINE_NAME
            price_text = await self._get_text(
                item,
                [
                    ".p-intro .price .currency",
                    ".p-intro .price",
                    ".price .currency",
                    ".price",
                    "[data-price]",
                    "[class*='price']",
                    "[class*='amount']",
                    ".journey-price",
                ],
            )
            price_match = re.search(r"(\d{2,5})", price_text)
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
                airline=airline,
                price=price,
                source=self.source,
                metadata={"record_type": "flight_list_page"},
                allow_empty_flight_no=True,
            )
        except Exception:
            return None

    async def _get_text(self, item: ElementHandle, selectors: List[str]) -> str:
        for selector in selectors:
            try:
                elem = await item.query_selector(selector)
                if not elem:
                    continue
                text = (await elem.inner_text()).strip()
                if text:
                    return text
            except Exception:
                continue
        return ""
