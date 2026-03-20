"""
Feizhu flight crawler.
"""

import asyncio
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from playwright.async_api import Browser, BrowserContext, ElementHandle, Page, async_playwright

from src.base_crawler import FlightCrawler
from src.config import Route
from src.exceptions import CrawlerError, NetworkError, ParseError, TimeoutError
from src.flight_record import normalize_flight_record
from src.utils import retry_with_backoff

logger = logging.getLogger(__name__)


FEIZHU_CITY_MAP = {
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


def get_feizhu_city_code(city_name: str) -> str:
    return FEIZHU_CITY_MAP.get(city_name, city_name)


class FeizhuCrawler(FlightCrawler):
    source = "feizhu"

    def __init__(self, headless: bool = True, username: str = "", password: str = ""):
        super().__init__(headless)
        self.playwright = None
        self.debug_html_path = Path("logs")
        self.debug_html_path.mkdir(parents=True, exist_ok=True)
        self.username = (username or "").strip()
        self.password = password or ""
        self.login_url = "https://www.fliggy.com/"
        self._login_attempted = False

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
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            await self.context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
            if self.username and self.password:
                self.page = await self.context.new_page()
                await self._login_fliggy()
            logger.info("[feizhu] browser initialized")
        except Exception as e:
            logger.error(f"[feizhu] browser init failed: {e}")
            raise CrawlerError(f"browser init failed: {e}")

    @retry_with_backoff(max_attempts=3, base_delay=5.0)
    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        if (not self.page) or self.page.is_closed():
            self.page = await self.context.new_page()

        results: List[Dict[str, Any]] = []
        for flight_date in route.dates.absolute_dates:
            try:
                results.extend(await self._search_single_date(route, flight_date))
            except Exception as e:
                logger.error(f"[feizhu] search failed {flight_date}: {e}")
        return results

    async def _search_single_date(
        self,
        route: Route,
        flight_date: date,
        retried_after_login: bool = False,
    ) -> List[Dict[str, Any]]:
        date_str = flight_date.strftime("%Y-%m-%d")
        url = self._build_search_url(route.from_city, route.to_city, date_str)

        try:
            if (not self.page) or self.page.is_closed():
                self.page = await self.context.new_page()

            response = await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            if not response or response.status != 200:
                raise NetworkError(f"page load failed: HTTP {response.status if response else 'None'}")

            if await self._is_login_page():
                if self.username and self.password and not retried_after_login:
                    await self._login_fliggy(force=True)
                    return await self._search_single_date(
                        route,
                        flight_date,
                        retried_after_login=True,
                    )
                raise CrawlerError("redirected to login page")

            await self._dismiss_popups()
            await asyncio.sleep(2)
            await self._wait_results_ready()

            flights = await self._parse_flights(route, flight_date)
            if not flights:
                await self._save_debug_html(route, date_str, "no_flights")
            return flights
        except Exception as e:
            await self._save_debug_snapshot(route, date_str, "error")
            raise ParseError(f"parse failed: {e}")

    async def _login_fliggy(self, force: bool = False) -> None:
        if not (self.username and self.password):
            return
        if self._login_attempted and not force:
            return
        self._login_attempted = True

        if not self.page:
            self.page = await self.context.new_page()

        try:
            await self.page.goto(self.login_url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(1)
            await self._dismiss_popups()
            await self._click_first(
                [
                    ".password-login-tab-item",
                    "text=密码登录",
                ],
                timeout=1200,
            )
            await asyncio.sleep(0.5)

            # Open login form if there is an entry button.
            await self._click_first(
                [
                    "text=登录",
                    "a:has-text('登录')",
                    "#F_site_nav_login a",
                    ".login-btn a",
                ],
                timeout=1200,
            )
            await asyncio.sleep(1)

            # Fill account and password fields.
            await self._fill_first(
                [
                    "input[name='username']",
                    "input[placeholder*='账号']",
                    "input[placeholder*='用户名']",
                    "input[type='text']",
                ],
                self.username,
            )
            await self._fill_first(
                [
                    "input[name='password']",
                    "input[type='password']",
                    "input[placeholder*='密码']",
                ],
                self.password,
            )
            await self._accept_login_agreements()

            # Some pages are two-step: click "下一步" first, then fill password.
            await self._click_first(["text=下一步", "button:has-text('下一步')"], timeout=1200)
            await asyncio.sleep(0.5)
            await self._fill_first(
                [
                    "input[name='password']",
                    "input[type='password']",
                    "input[placeholder*='密码']",
                ],
                self.password,
            )
            await self._accept_login_agreements()
            await self._click_first(
                [
                    "#login-form .fm-submit",
                    "button:has-text('登录')",
                    "text=登录",
                    ".login-button",
                    "input[type='submit']",
                ],
                timeout=1500,
            )
            await asyncio.sleep(2.5)
            await self._refresh_active_page()
            await self._dismiss_after_login_dialogs()
            await asyncio.sleep(1)
            await self._dismiss_after_login_dialogs()
            logger.info("[feizhu] login flow attempted")
        except Exception as e:
            logger.warning(f"[feizhu] login attempt failed: {e}")

    async def ensure_logged_in(self) -> None:
        """Public hook used by monitor workflow: login first, then search."""
        if self.username and self.password:
            await self._login_fliggy(force=True)

    async def _click_first(self, selectors: List[str], timeout: int = 1000) -> bool:
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                if await locator.count() and await locator.is_visible():
                    await locator.click(timeout=timeout)
                    return True
            except Exception:
                continue
        return False

    async def _fill_first(self, selectors: List[str], value: str) -> bool:
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                if await locator.count() and await locator.is_visible():
                    await locator.fill("")
                    await locator.type(value, delay=25)
                    return True
            except Exception:
                continue
        return False

    async def _dismiss_after_login_dialogs(self) -> None:
        # Login success often leads to an announcement modal that needs one extra confirm click.
        await self._click_first(
            [
                "#J_Flight_Notify_Close_Btn",
                ".dialog-btn-ok",
                ".notify-button",
                ".next-dialog-footer button:has-text('我知道了')",
                ".next-dialog-footer button:has-text('确定')",
                ".next-dialog-footer button:has-text('确认')",
                "button:has-text('同意')",
                "button:has-text('我知道了')",
                "button:has-text('知道了')",
                "button:has-text('同意')",
                "button:has-text('确认')",
                "button:has-text('确定')",
                "text=同意",
                "text=我知道了",
                "text=知道了",
                "text=同意",
                "text=确认",
                "text=确定",
            ],
            timeout=1500,
        )

    async def _accept_login_agreements(self) -> None:
        # Taobao password login requires the agreement checkbox before submit.
        try:
            checkbox = self.page.locator("#fm-agreement-checkbox").first
            if await checkbox.count():
                is_checked = await checkbox.is_checked()
                if not is_checked:
                    await checkbox.check(force=True)
                    await asyncio.sleep(0.2)
        except Exception:
            pass

        await self._click_first(
            [
                ".dialog-btn-ok",
                "button:has-text('同意')",
                "text=同意",
            ],
            timeout=1200,
        )

    async def _refresh_active_page(self) -> None:
        # Some login flows may close the current tab and keep result in another page.
        if self.page and not self.page.is_closed():
            return
        pages = self.context.pages if self.context else []
        for p in reversed(pages):
            if not p.is_closed():
                self.page = p
                return
        if self.context:
            self.page = await self.context.new_page()

    async def _is_login_page(self) -> bool:
        try:
            title = await self.page.title()
            if "登录" in title or "login" in title.lower():
                return True
            body = await self.page.inner_text("body")
            return ("使用账号登录" in body) or ("请输入账号" in body)
        except Exception:
            return False

    def _build_search_url(self, from_city: str, to_city: str, date_str: str) -> str:
        from_code = get_feizhu_city_code(from_city)
        to_code = get_feizhu_city_code(to_city)
        return (
            "https://sjipiao.fliggy.com/flight_search_result.htm"
            f"?tripType=0&depCity={from_code}&arrCity={to_code}"
            f"&depDate={date_str}"
            f"&depCityName={quote(from_city)}&arrCityName={quote(to_city)}"
        )

    async def _dismiss_popups(self) -> None:
        close_selectors = [
            ".next-dialog-close",
            ".dialog-close",
            ".close-btn",
            ".btn-close",
            ".J_Close",
            ".next-dialog .next-icon-close",
            ".next-modal .next-icon-close",
            ".next-drawer-close",
            "[class*='dialog'] [class*='close']",
            "[class*='modal'] [class*='close']",
            "[class*='popup'] [class*='close']",
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

        for text in ["关闭", "我知道了", "知道了", "同意", "接受", "确定", "Close", "I know", "OK", "Accept", "Confirm"]:
            try:
                locator = self.page.get_by_text(text).first
                if await locator.count() and await locator.is_visible():
                    await locator.click(timeout=800)
                    await asyncio.sleep(0.2)
            except Exception:
                continue

    async def _wait_results_ready(self) -> None:
        selectors = [
            ".flight-list-item",
            ".J_FlightItem",
            "[class*='flight-list-item']",
            "[class*='FlightItem']",
        ]
        for selector in selectors:
            try:
                await self.page.wait_for_selector(selector, timeout=8000)
                return
            except Exception:
                continue
        raise TimeoutError("flight list selector not found in page")

    async def _parse_flights(self, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        selectors = [
            ".flight-list-item",
            ".J_FlightItem",
            "[class*='flight-list-item']",
            "[class*='FlightItem']",
        ]

        items: List[ElementHandle] = []
        for selector in selectors:
            items = await self.page.query_selector_all(selector)
            if items:
                logger.info(f"[feizhu] found {len(items)} flight nodes via {selector}")
                break

        flights: List[Dict[str, Any]] = []
        for item in items:
            flight = await self._parse_single_flight(item, route, flight_date)
            if flight:
                flights.append(flight)

        logger.info(f"[feizhu] parsed {len(flights)} flights")
        return flights

    async def _parse_single_flight(
        self,
        item: ElementHandle,
        route: Route,
        flight_date: date,
    ) -> Optional[Dict[str, Any]]:
        try:
            raw_text = await item.inner_text()
            raw_text = raw_text.strip()
            if not raw_text:
                return None

            flight_no = await self._get_text(
                item,
                [
                    "[data-flight-no]",
                    ".J_line",
                    ".J_TestFlight",
                    ".flight-no",
                    "[class*='flight-no']",
                ],
            )

            airline = await self._get_text(
                item,
                [
                    "[data-airline]",
                    ".airline-name",
                    ".flight-line .J_line",
                    "[class*='airline']",
                ],
            )

            # Typical text is like "南航CZ3558" or "国航CA3379"
            carrier_blob = " ".join([airline or "", flight_no or "", raw_text]).strip()
            flight_match = re.search(r"\b([A-Z0-9]{2,3}\d{3,4})\b", carrier_blob)
            flight_no = flight_match.group(1) if flight_match else "Unknown"

            if not airline:
                airline = carrier_blob
            airline = airline.replace(flight_no, "").strip() if flight_no != "Unknown" else airline.strip()
            if not airline:
                m = re.search(r"([\u4e00-\u9fa5]{2,}(航空|航司|航班|航空公司)?)", carrier_blob)
                airline = m.group(1) if m else "Unknown"

            price_text = await self._get_text(
                item,
                [
                    "[data-price]",
                    ".price",
                    "[class*='price']",
                ],
            )
            if not price_text:
                price_text = raw_text
            price_match = re.search(r"(?:¥|￥)?\s*(\d{2,5})", price_text)
            if not price_match:
                return None
            price = int(price_match.group(1))
            if price < 10:
                return None

            departure_airport = await self._get_text(
                item,
                [".departure-airport", "[class*='departure']", "[data-departure-port]"],
            )
            arrival_airport = await self._get_text(
                item,
                [".arrival-airport", "[class*='arrival']", "[data-arrival-port]"],
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
        except Exception as e:
            logger.debug(f"[feizhu] parse single flight failed: {e}")
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

    async def _save_debug_html(self, route: Route, date_str: str, tag: str) -> None:
        try:
            filename = f"feizhu_{route.from_city}_{route.to_city}_{date_str}_{tag}.html"
            path = self.debug_html_path / filename
            with open(path, "w", encoding="utf-8") as f:
                f.write(await self.page.content())
            logger.info(f"[feizhu] debug html saved: {path}")
        except Exception as e:
            logger.debug(f"[feizhu] save debug html failed: {e}")

    async def _save_debug_snapshot(self, route: Route, date_str: str, tag: str) -> None:
        try:
            await self._save_debug_html(route, date_str, tag)
            png_name = f"feizhu_{route.from_city}_{route.to_city}_{date_str}_{tag}.png"
            png_path = self.debug_html_path / png_name
            await self.page.screenshot(path=str(png_path), full_page=True)
            logger.info(f"[feizhu] debug screenshot saved: {png_path}")
        except Exception as e:
            logger.debug(f"[feizhu] save debug snapshot failed: {e}")

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

