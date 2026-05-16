from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
import asyncio
import logging
import random

from playwright.async_api import Page

from src.config import Route
from src.cookie_manager import CookieManager
from src.stealth import get_random_desktop_ua, get_random_viewport, get_stealth_init_script

logger = logging.getLogger(__name__)

COMMON_ANTIBOT_SIGNALS = [
    "验证", "captcha", "拦截", "禁止访问",
    "Too Many Requests", "访问频繁", "安全验证",
]


class FlightCrawler(ABC):
    """Abstract base class for transport data sources."""

    source: str

    def __init__(
        self,
        headless: bool = True,
        use_stealth: bool = True,
        mobile_mode: bool = False,
        cookie_dir: Optional[Path] = None,
    ):
        self.headless = headless
        self.use_stealth = use_stealth
        self.mobile_mode = mobile_mode
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self.cookie_manager = CookieManager(cookie_dir) if cookie_dir else None

    async def _apply_stealth_to_context(self) -> None:
        if not self.context or not self.use_stealth:
            return
        await self.context.add_init_script(get_stealth_init_script())
        logger.info("[%s] Stealth mode applied", self.source)

    async def _load_cookies_to_context(self) -> None:
        if not self.context or not self.cookie_manager:
            return
        cookies = await self.cookie_manager.load_cookies(self.source)
        if cookies:
            await self.context.add_cookies(cookies)
            logger.info("[%s] Loaded %d cookies", self.source, len(cookies))

    async def _save_cookies_from_context(self) -> None:
        if not self.context or not self.cookie_manager:
            return
        try:
            cookies = await self.context.cookies()
            await self.cookie_manager.save_cookies(self.source, cookies)
        except Exception as exc:
            logger.warning("[%s] Failed to save cookies: %s", self.source, exc)

    async def _random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        await asyncio.sleep(random.uniform(min_seconds, max_seconds))

    def _get_browser_args(self) -> List[str]:
        return [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-extensions",
            "--disable-gpu",
        ]

    def _get_context_options(self) -> Dict[str, Any]:
        return {
            "viewport": get_random_viewport(mobile=self.mobile_mode),
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "user_agent": get_random_desktop_ua(),
            "extra_http_headers": {
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        }

    @abstractmethod
    async def init(self) -> None:
        """Initialize source resources."""

    @abstractmethod
    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        """Search records and return normalized transport records."""

    async def close(self) -> None:
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

    async def _check_antibot(self, page: Page, extra_signals: List[str] = None) -> bool:
        try:
            title = await page.title()
            url = page.url
            signals = COMMON_ANTIBOT_SIGNALS + (extra_signals or [])
            haystack = f"{title}\n{url}".lower()
            return any(signal.lower() in haystack for signal in signals)
        except Exception:
            return False

    async def _save_debug_snapshot(
        self, page: Page, route: Route, flight_date: date, suffix: str
    ) -> None:
        safe_name = f"{self.source}_{route.from_city}_{route.to_city}_{flight_date.isoformat()}_{suffix}"
        debug_path = Path("logs")
        debug_path.mkdir(parents=True, exist_ok=True)
        html_path = debug_path / f"{safe_name}.html"
        png_path = debug_path / f"{safe_name}.png"

        try:
            html_path.write_text(await page.content(), encoding="utf-8")
        except Exception:
            pass

        try:
            await page.screenshot(path=str(png_path), full_page=True)
        except Exception:
            pass
