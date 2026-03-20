"""
China Southern official-site crawler.
"""

import asyncio
import json
import logging
import math
import random
import re
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlencode

from playwright.async_api import ElementHandle, Page, async_playwright

from src.base_crawler import FlightCrawler
from src.captcha_solver import get_captcha_solver
from src.config import Route
from src.exceptions import AntiBotError, BrowserCrashError, CrawlerError, ParseError
from src.flight_record import normalize_flight_record
from src.utils import retry_with_backoff

logger = logging.getLogger(__name__)


CSAIR_CITY_CODE_MAP = {
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

CSAIR_AIRLINE_NAME = "南方航空"
CSAIR_HOMEPAGE_URL = "https://www.csair.com/cn/index.shtml"
CSAIR_DIRECT_QUERY_URL = "https://b2c.csair.com/portal/main/flight/direct/query"


def get_csair_city_code(city_name: str) -> str:
    return CSAIR_CITY_CODE_MAP.get(city_name, city_name)


class CsairCrawler(FlightCrawler):
    source = "csair"

    def __init__(self, headless: bool = True, cookie_dir: Path = None):
        """初始化南航爬虫。

        Args:
            headless: 是否无头模式运行
            cookie_dir: cookie 存储目录，默认为 data/cookies
        """
        super().__init__(
            headless=headless,
            use_stealth=True,
            mobile_mode=False,
            cookie_dir=cookie_dir or Path("data/cookies"),
        )
        self.playwright = None
        self.debug_path = Path("logs")
        self.debug_path.mkdir(parents=True, exist_ok=True)
        self._session_warmed = False
        self._query_cooldown_until = 0.0

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def init(self) -> None:
        """初始化浏览器资源，使用基类的反检测功能。"""
        try:
            self.playwright = await async_playwright().start()

            # 使用基类方法获取浏览器参数，并添加南航特定的额外参数
            browser_args = self._get_browser_args() + [
                "--disable-software-rasterizer",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-breakpad",
                "--disable-component-extensions-with-background-pages",
                "--disable-features=TranslateUI,BlinkGenPropertyTrees",
                "--disable-ipc-flooding-protection",
                "--disable-renderer-backgrounding",
                "--disable-sync",
                "--force-color-profile=srgb",
                "--metrics-recording-only",
                "--no-first-run",
                "--enable-automation=false",
                "--password-store=basic",
                "--use-mock-keychain",
                "--disable-site-isolation-trials",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--start-maximized",
            ]

            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=browser_args,
                slow_mo=10,
            )

            # 使用基类方法获取上下文选项，并添加南航特定的配置
            context_options = self._get_context_options()
            context_options.update({
                "viewport": None,  # 使用浏览器窗口的实际大小
                "extra_http_headers": {
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Referer": "https://b2c.csair.com/",
                    "Sec-Ch-Ua": '"Chromium";v="120", "Not(A:Brand";v="24", "Google Chrome";v="120"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1",
                    "DNT": "1",
                },
                "color_scheme": "light",
                "reduced_motion": "no-preference",
                "ignore_https_errors": True,
                "java_script_enabled": True,
            })

            self.context = await self.browser.new_context(**context_options)

            # 使用基类方法应用 stealth 模式
            await self._apply_stealth_to_context()

            # 添加南航特定的反检测脚本
            await self.context.add_init_script(
                """
                // 基础伪装
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                delete navigator.__proto__.webdriver;

                // 插件伪装
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                    ]
                });

                // 语言和平台
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });
                Object.defineProperty(navigator, 'vendor', { get: () => 'Google Inc.' });
                Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

                // 硬件信息
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });

                // Chrome 对象
                window.chrome = {
                    runtime: { id: undefined },
                    loadTimes: function(){},
                    csi: function(){},
                    app: {
                        isInstalled: false,
                        InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                        RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
                    }
                };
                Object.defineProperty(window, 'chrome', { value: window.chrome });

                // Permissions API
                const _origQuery = window.navigator.permissions.query.bind(navigator.permissions);
                window.navigator.permissions.query = (parameters) =>
                    parameters.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : _origQuery(parameters);

                // 屏幕属性
                const screenProp = {
                    0: 1920, 1: 1080,
                    availLeft: 0, availTop: 0,
                    availWidth: 1920, availHeight: 1040,
                    width: 1920, height: 1080,
                    colorDepth: 24, pixelDepth: 24,
                    orientation: { type: 'landscape-primary', angle: 0 }
                };
                for (const [key, val] of Object.entries(screenProp)) {
                    Object.defineProperty(screen, key, { get: () => val });
                }

                // WebGL 指纹
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) return 'Intel Inc.';
                    if (parameter === 37446) return 'Intel(R) UHD Graphics 630';
                    return getParameter.call(this, parameter);
                };

                // Canvas 指纹噪声
                const getImageData = CanvasRenderingContext2D.prototype.getImageData;
                CanvasRenderingContext2D.prototype.getImageData = function() {
                    const imageData = getImageData.apply(this, arguments);
                    for (let i = 0; i < imageData.data.length; i += 4) {
                        imageData.data[i] += Math.random() * 2 - 1;
                    }
                    return imageData;
                };

                // 掩盖自动化特征
                window.outerHeight = window.screen.height;
                window.outerWidth = window.screen.width;

                // 禁用部分检测函数
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );

                // 伪造 navigator.connection
                Object.defineProperty(navigator, 'connection', {
                    get: () => ({
                        effectiveType: '4g',
                        rtt: 50,
                        downlink: 10,
                        saveData: false,
                        addEventListener: () => {},
                        removeEventListener: () => {}
                    })
                });
                """
            )

            # 使用基类方法加载已保存的 cookies
            await self._load_cookies_to_context()

            logger.info("[csair] Browser initialized with stealth mode and cookie persistence")

        except Exception as exc:
            raise BrowserCrashError(f"csair browser init failed: {exc}") from exc

    @retry_with_backoff(max_attempts=3, base_delay=4.0)
    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for index, flight_date in enumerate(sorted(route.dates.absolute_dates)):
            if index:
                await self._human_pause(8.0, 14.0)

            if self._should_skip_query():
                logger.info(
                    "[csair] direct query is cooling down for %s %s -> %s",
                    flight_date,
                    route.from_city,
                    route.to_city,
                )
                raise AntiBotError("csair query is cooling down after risk-control detection")

            results.extend(await self._search_single_date(route, flight_date))
        return results

    async def _search_single_date(self, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        if not self.context:
            raise CrawlerError("csair browser context is not initialized")

        await self._warm_session()
        page = await self._new_page()  # 使用新方法创建页面
        captured_payloads: List[Dict[str, Any]] = []
        captured_errors: List[str] = []
        response_tasks: List[asyncio.Task] = []

        async def capture_response(response) -> None:
            if CSAIR_DIRECT_QUERY_URL not in response.url:
                return
            try:
                payload_text = await response.text()
            except Exception as exc:
                captured_errors.append(f"failed to read csair response: {exc}")
                return

            if self._is_antibot_payload(payload_text):
                captured_errors.append("csair direct query hit anti-bot verification")
                return

            try:
                captured_payloads.append(json.loads(payload_text))
            except json.JSONDecodeError:
                captured_errors.append("csair direct query returned non-JSON payload")

        page.on("response", lambda response: response_tasks.append(asyncio.create_task(capture_response(response))))

        try:
            await self._submit_homepage_search(page, route, flight_date)
            await page.wait_for_timeout(random.randint(2000, 3000))  # 减少等待时间
            if response_tasks:
                await asyncio.gather(*response_tasks, return_exceptions=True)

            dom_flights = await self._parse_dom_list(page, route, flight_date)
            if dom_flights:
                await self._save_debug_snapshot(page, route, flight_date, "page")
                if captured_payloads:
                    await self._save_payload_snapshot(captured_payloads, route, flight_date)
                return dom_flights

            if await self._page_shows_antibot(page):
                logger.info("[csair] WAF slider detected, attempting to solve...")
                solved = await self._try_solve_slider(page)
                if solved:
                    logger.info("[csair] slider solved, continuing...")
                    await page.wait_for_timeout(random.randint(3000, 5000))
                    dom_flights = await self._parse_dom_list(page, route, flight_date)
                    if dom_flights:
                        return dom_flights
                # 滑块未解决，激活 cooldown
                self._activate_query_cooldown()
                raise AntiBotError("csair booking page requires verification")

            if captured_errors and not captured_payloads:
                self._activate_query_cooldown()
                raise AntiBotError(captured_errors[0])

            flights = self._parse_payloads(captured_payloads, route, flight_date)
            if not flights:
                raise ParseError("csair did not return usable flight data")

            await self._save_debug_snapshot(page, route, flight_date, "page")
            await self._save_payload_snapshot(captured_payloads, route, flight_date)
            return flights
        except (AntiBotError, ParseError):
            await self._save_debug_snapshot(page, route, flight_date, "error")
            if captured_payloads:
                await self._save_payload_snapshot(captured_payloads, route, flight_date)
            raise
        except Exception as exc:
            await self._save_debug_snapshot(page, route, flight_date, "error")
            if captured_payloads:
                await self._save_payload_snapshot(captured_payloads, route, flight_date)
            raise CrawlerError(f"csair query failed: {exc}") from exc
        finally:
            await page.close()

    async def _submit_homepage_search(self, page: Page, route: Route, flight_date: date) -> None:
        await self._human_pause(2.0, 4.5)
        await page.goto(CSAIR_HOMEPAGE_URL, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(random.randint(3000, 6000))

        await page.locator("li.flight.nav-tab").first.click(timeout=5000)
        await page.wait_for_timeout(random.randint(800, 1600))

        from_code = get_csair_city_code(route.from_city)
        to_code = get_csair_city_code(route.to_city)
        date_text = flight_date.isoformat()

        # 出发城市：点击 → 清空 → 逐字输入
        dep_city_input = page.locator('#fDepCity')
        await dep_city_input.click(timeout=5000)
        await page.wait_for_timeout(random.randint(300, 500))
        await dep_city_input.fill('')
        await page.wait_for_timeout(random.randint(200, 400))

        # 逐字输入城市名
        for char in route.from_city:
            await dep_city_input.type(char, delay=random.randint(100, 200))
        await page.wait_for_timeout(random.randint(800, 1200))

        # 尝试点击下拉列表
        try:
            city_item = page.locator('.city-list li, .suggest-item, [class*="cityItem"]').first
            await city_item.click(timeout=3000)
        except Exception:
            await page.keyboard.press('Enter')
        await page.wait_for_timeout(random.randint(500, 800))

        # 到达城市：同样操作
        arr_city_input = page.locator('#fArrCity')
        await arr_city_input.click(timeout=5000)
        await page.wait_for_timeout(random.randint(300, 500))
        await arr_city_input.fill('')
        await page.wait_for_timeout(random.randint(200, 400))

        for char in route.to_city:
            await arr_city_input.type(char, delay=random.randint(100, 200))
        await page.wait_for_timeout(random.randint(800, 1200))

        try:
            city_item = page.locator('.city-list li, .suggest-item, [class*="cityItem"]').first
            await city_item.click(timeout=3000)
        except Exception:
            await page.keyboard.press('Enter')
        await page.wait_for_timeout(random.randint(500, 800))

        # 日期和城市代码用 evaluate 注入（南航日期选择器是自定义组件，type 无效）
        await page.evaluate(
            """
            ({ fromCode, toCode, dateText }) => {
                const setValue = (el, value) => {
                    if (!el) return;
                    el.value = value;
                    el.setAttribute('value', value);
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                };
                setValue(document.querySelector('#city1_code'), fromCode);
                setValue(document.querySelector('#city2_code'), toCode);
                setValue(document.querySelector('#fDepDate'), dateText);
            }
            """,
            {"fromCode": from_code, "toCode": to_code, "dateText": date_text},
        )

        await page.wait_for_timeout(random.randint(1000, 2200))
        search_button = page.locator(".searchBtn.searchFlight").first
        await search_button.scroll_into_view_if_needed()
        # 搜索按钮先 hover 停留再点击
        await search_button.hover()
        await page.wait_for_timeout(random.randint(300, 600))
        await search_button.click(timeout=10000)
        try:
            await page.wait_for_url(re.compile(r"b2c\.csair\.com/.*/booking/index\.html"), timeout=45000)
        except Exception:
            pass
        await page.wait_for_load_state("domcontentloaded")

    async def _warm_session(self) -> None:
        if self._session_warmed or not self.context:
            return

        page = await self.context.new_page()
        try:
            # 确保窗口最大化
            await page.evaluate("() => { if (window.screenX === 0 && window.screenY === 0) { window.moveTo(0, 0); window.resizeTo(screen.availWidth, screen.availHeight); } }")
            await page.goto(CSAIR_HOMEPAGE_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(random.randint(3000, 6000))
            self._session_warmed = True
        except Exception as exc:
            logger.info("[csair] warm-up page skipped: %s", exc)
        finally:
            await page.close()

    async def _new_page(self):
        """创建新页面并确保窗口最大化。"""
        page = await self.context.new_page()
        # 确保窗口最大化
        try:
            await page.evaluate("""
                () => {
                    if (window.outerWidth < screen.availWidth || window.outerHeight < screen.availHeight) {
                        window.moveTo(0, 0);
                        window.resizeTo(screen.availWidth, screen.availHeight);
                    }
                }
            """)
        except Exception:
            pass  # 忽略错误
        return page

    async def _human_pause(self, min_seconds: float, max_seconds: float) -> None:
        await asyncio.sleep(random.uniform(min_seconds, max_seconds))

    def _activate_query_cooldown(self, cooldown_seconds: int = 1800) -> None:
        self._query_cooldown_until = time.monotonic() + cooldown_seconds

    def _should_skip_query(self) -> bool:
        return time.monotonic() < self._query_cooldown_until

    async def _page_shows_antibot(self, page: Page) -> bool:
        try:
            # DOM 检测（优先，更可靠）
            waf_block = page.locator('#waf_nc_block')
            if await waf_block.count() and await waf_block.is_visible():
                return True
            title = await page.title()
            body = await page.locator("body").inner_text()
        except Exception:
            return False
        return self._is_antibot_payload(f"{title}\n{body}")

    def _is_antibot_payload(self, text: str) -> bool:
        if not text:
            return False
        signals = [
            "aliyun_waf",
            "waf_nc_block",
            "waf-nc-wrapper",
            "访问验证",
            "为了更好的访问体验",
            "captcha",
            "TraceID",
            "CF_APP_WAF",
        ]
        lowered = text.lower()
        return any(signal.lower() in lowered for signal in signals)

    async def _parse_dom_list(self, page: Page, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        selectors = [
            ".zls-flight-cell",
            ".zls-flight .zls-flight-cell",
        ]
        items: List[ElementHandle] = []
        for selector in selectors:
            try:
                items = await page.query_selector_all(selector)
            except Exception:
                items = []
            if items:
                logger.info("[csair] found %s flight nodes via %s", len(items), selector)
                break

        flights: List[Dict[str, Any]] = []
        seen = set()
        for item in items:
            flight = await self._parse_dom_flight_item(item, route, flight_date)
            if not flight:
                continue
            key = (flight["flight_no"], flight["price"], flight["route_from"], flight["route_to"])
            if key in seen:
                continue
            seen.add(key)
            flights.append(flight)
        return flights

    async def _parse_dom_flight_item(
        self,
        item: ElementHandle,
        route: Route,
        flight_date: date,
    ) -> Dict[str, Any] | None:
        try:
            flight_no_text = await self._get_text(item, [".zls-flgno-info", ".zls-flgno"])
            flight_match = re.search(r"\b([A-Z0-9]{2,3}\d{3,4})\b", flight_no_text)
            flight_no = flight_match.group(1) if flight_match else ""
            if not flight_no:
                return None

            plane_text = await self._get_text(item, [".zls-flgplane"])
            departure_time = await self._get_text(item, [".zls-flgtime-dep"])
            arrival_time = await self._get_text(item, [".zls-flgtime-arr"])
            departure_airport = await self._get_text(item, [".zls-flgtime-dep .zls-flplace"])
            arrival_airport = await self._get_text(item, [".zls-flgtime-arr .zls-flplace"])
            duration = await self._get_text(item, [".zls-flg-time"])

            price = await self._extract_dom_lowest_price(item)
            if price is None:
                return None

            dep_code = (await item.get_attribute("data-dep") or "").strip().upper()
            arr_code = (await item.get_attribute("data-arr") or "").strip().upper()
            metadata: Dict[str, Any] = {"record_type": "booking_page_dom"}
            if departure_time:
                metadata["departure_time"] = self._extract_clock_time(departure_time)
            if arrival_time:
                metadata["arrival_time"] = self._extract_clock_time(arrival_time)
            if duration:
                metadata["duration"] = duration.strip()
            if plane_text:
                metadata["plane_name"] = plane_text.strip()
            if dep_code:
                metadata["departure_airport_code"] = dep_code
            if arr_code:
                metadata["arrival_airport_code"] = arr_code

            return normalize_flight_record(
                route_from=route.from_city,
                route_to=route.to_city,
                flight_date=flight_date,
                flight_no=flight_no,
                airline=self._guess_airline_name(flight_no),
                price=price,
                source=self.source,
                departure_airport=departure_airport,
                arrival_airport=arrival_airport,
                metadata=metadata,
            )
        except Exception:
            return None

    async def _extract_dom_lowest_price(self, item: ElementHandle) -> int | None:
        cabins = await item.query_selector_all(".zls-cabin-cell")
        prices: List[int] = []
        for cabin in cabins:
            try:
                cabin_class = (await cabin.get_attribute("class") or "").lower()
                if "disabled" in cabin_class:
                    continue
                raw_value = (await cabin.get_attribute("data-value") or "").strip()
                if self._is_valid_price(raw_value):
                    prices.append(int(raw_value))
                    continue
                raw_text = (await cabin.inner_text()).strip()
                match = re.search(r"(\d{2,5})", raw_text)
                if match:
                    prices.append(int(match.group(1)))
            except Exception:
                continue
        return min(prices) if prices else None

    def _extract_clock_time(self, text: str) -> str:
        match = re.search(r"\b(\d{2}:\d{2})\b", text)
        return match.group(1) if match else text.strip()

    def _parse_payloads(
        self,
        payloads: List[Dict[str, Any]],
        route: Route,
        flight_date: date,
    ) -> List[Dict[str, Any]]:
        flights: List[Dict[str, Any]] = []
        seen = set()
        for payload in payloads:
            for flight in self._parse_single_payload(payload, route, flight_date):
                key = (flight["flight_no"], flight["price"], flight["route_from"], flight["route_to"])
                if key in seen:
                    continue
                seen.add(key)
                flights.append(flight)
        return flights

    def _parse_single_payload(
        self,
        payload: Dict[str, Any],
        route: Route,
        flight_date: date,
    ) -> List[Dict[str, Any]]:
        if not payload.get("success") or not payload.get("data"):
            return []

        data = payload["data"]
        segments = data.get("segment") or data.get("segments") or []
        if isinstance(segments, dict):
            segments = [segments]
        if not segments:
            return []

        segment = segments[0]
        segment_date = (segment.get("date") or "").replace("-", "")
        if segment_date and segment_date != flight_date.strftime("%Y%m%d"):
            return []

        airports = self._extract_named_map(data.get("airports"))
        flights = segment.get("dateFlight", {}).get("flight") or segment.get("flight") or []
        normalized: List[Dict[str, Any]] = []

        for item in flights:
            price = self._extract_lowest_price(item)
            flight_no = (item.get("flightNo") or "").strip().upper()
            if not flight_no or price is None:
                continue

            dep_time = self._format_time(item.get("depTime"))
            arr_time = self._format_time(item.get("arrTime"))
            dep_port = (item.get("depPort") or "").strip().upper()
            arr_port = (item.get("arrPort") or "").strip().upper()
            departure_airport = airports.get(dep_port, dep_port)
            arrival_airport = airports.get(arr_port, arr_port)
            duration = (item.get("timeDuringFlight") or "").strip()
            plane = (item.get("plane") or "").strip()

            metadata: Dict[str, Any] = {"record_type": "api_direct_query"}
            if dep_time:
                metadata["departure_time"] = dep_time
            if arr_time:
                metadata["arrival_time"] = arr_time
            if duration:
                metadata["duration"] = duration
            if plane:
                metadata["plane_code"] = plane
            if dep_port:
                metadata["departure_airport_code"] = dep_port
            if arr_port:
                metadata["arrival_airport_code"] = arr_port

            normalized.append(
                normalize_flight_record(
                    route_from=route.from_city,
                    route_to=route.to_city,
                    flight_date=flight_date,
                    flight_no=flight_no,
                    airline=self._guess_airline_name(flight_no),
                    price=price,
                    source=self.source,
                    departure_airport=departure_airport,
                    arrival_airport=arrival_airport,
                    metadata=metadata,
                )
            )

        return normalized

    def _extract_named_map(self, raw_items: Any) -> Dict[str, str]:
        named_map: Dict[str, str] = {}
        if isinstance(raw_items, dict):
            for code, value in raw_items.items():
                if isinstance(value, dict):
                    named_map[str(code).upper()] = (
                        value.get("zhName") or value.get("name") or value.get("airportName") or str(code)
                    )
                else:
                    named_map[str(code).upper()] = str(value)
            return named_map

        if isinstance(raw_items, list):
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                code = item.get("code") or item.get("airportCode") or item.get("iata")
                if not code:
                    continue
                named_map[str(code).upper()] = (
                    item.get("zhName") or item.get("name") or item.get("airportName") or str(code)
                )
        return named_map

    def _extract_lowest_price(self, flight: Dict[str, Any]) -> int | None:
        candidates: List[int] = []

        for cabin in flight.get("cabin") or []:
            adult_price = cabin.get("adultPrice")
            if self._is_valid_price(adult_price):
                candidates.append(int(adult_price))

            for sec in cabin.get("secondPrices") or []:
                for price in sec.get("price") or []:
                    adult = price.get("adult")
                    if self._is_valid_price(adult):
                        candidates.append(int(adult))

        return min(candidates) if candidates else None

    def _is_valid_price(self, value: Any) -> bool:
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return False
        return numeric >= 10

    def _format_time(self, raw_time: Any) -> str:
        if raw_time is None:
            return ""
        text = str(raw_time).strip()
        if re.fullmatch(r"\d{4}", text):
            return f"{text[:2]}:{text[2:]}"
        return text

    def _guess_airline_name(self, flight_no: str) -> str:
        if flight_no.startswith("CZ"):
            return CSAIR_AIRLINE_NAME
        return flight_no[:2] if flight_no else CSAIR_AIRLINE_NAME

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

    async def _save_debug_snapshot(
        self,
        page: Page,
        route: Route,
        flight_date: date,
        suffix: str,
    ) -> None:
        safe_name = f"csair_{route.from_city}_{route.to_city}_{flight_date.isoformat()}_{suffix}"
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

    async def _save_payload_snapshot(
        self,
        payloads: List[Dict[str, Any]],
        route: Route,
        flight_date: date,
    ) -> None:
        payload_path = self.debug_path / f"csair_{route.from_city}_{route.to_city}_{flight_date.isoformat()}_payload.json"
        try:
            payload_path.write_text(json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    async def _try_solve_slider(self, page: Page) -> bool:
        """尝试通过阿里云 WAF aliyunCaptcha 滑块验证。返回 True 表示可能已通过。"""
        try:
            # 立即开始，不等待
            await page.wait_for_timeout(50)

            # 阿里云新版 aliyunCaptcha 的滑块选择器
            slider_selectors = [
                '#aliyunCaptcha-sliding-slider',
                '.aliyunCaptcha-sliding-slider',
                '.btn_slide',
            ]
            btn = None
            for selector in slider_selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.count():
                        logger.info("[csair] found slider via selector: %s", selector)
                        break
                except Exception:
                    continue

            if not btn or not await btn.count():
                logger.info("[csair] slider button not found")
                return False

            btn_box = await btn.bounding_box()
            if not btn_box:
                logger.info("[csair] slider button bounding box not available")
                return False

            logger.info("[csair] slider button box: x=%s, y=%s, w=%s, h=%s",
                       btn_box['x'], btn_box['y'], btn_box['width'], btn_box['height'])

            # 计算滑动距离 - 滑到最右边
            slide_distance = int(320 - btn_box['width'] - 10)  # 几乎滑到底

            # 尝试使用打码服务获取精确缺口位置
            captcha_solver = get_captcha_solver()
            if captcha_solver:
                try:
                    gap_x = await captcha_solver.solve_slider(page)
                    if gap_x:
                        slide_distance = int(gap_x - btn_box['width'] / 2)
                        logger.info("[csair] 打码服务返回缺口位置: %s, 滑动距离: %s", gap_x, slide_distance)
                except Exception as e:
                    logger.warning("[csair] 打码服务失败: %s", e)

            start_x = btn_box['x'] + btn_box['width'] / 2
            start_y = btn_box['y'] + btn_box['height'] / 2

            logger.info("[csair] start slide, distance=%s", slide_distance)

            # 立即开始滑动，不hover
            distances_to_try = [
                slide_distance + 40,
                slide_distance + 50,
                slide_distance + 30,
                slide_distance + 20,
                slide_distance + 10,
                slide_distance,
                slide_distance - 10,
                slide_distance - 20,
                slide_distance + 60,
            ]

            for dist_idx, distance in enumerate(distances_to_try):
                logger.info("[csair] attempting slide with distance: %s (attempt %d/%d)",
                           distance, dist_idx + 1, len(distances_to_try))
                try:
                    success = await self._slider_attempt_with_retry(page, start_x, start_y, distance)
                    if success:
                        logger.info("[csair] slider solved with distance: %s", distance)
                        # 成功后等待页面跳转
                        await page.wait_for_timeout(random.randint(2000, 4000))
                        return True
                except Exception as attempt_exc:
                    logger.debug("[csair] slider attempt %d failed: %s", dist_idx + 1, attempt_exc)
                    # 如果是浏览器崩溃，也认为可能成功了
                    if 'crashed' in str(attempt_exc).lower() or 'target crashed' in str(attempt_exc).lower():
                        logger.info("[csair] browser crashed during slider, possible success")
                        # 等待一下看看是否能恢复
                        await page.wait_for_timeout(random.randint(2000, 4000))
                        # 尝试检查页面状态
                        try:
                            if not await page.locator('#waf_nc_block').is_visible(timeout=1000):
                                return True
                        except Exception:
                            # 无法检查，假设成功
                            return True

                # 失败后等待重置
                await page.wait_for_timeout(random.randint(1000, 2000))

                # 检查是否已经通过（页面可能已经跳转）
                try:
                    if not await page.locator('#waf_nc_block').is_visible(timeout=2000):
                        logger.info("[csair] slider block disappeared after attempt %d", dist_idx + 1)
                        return True
                except Exception as check_exc:
                    logger.debug("[csair] visibility check failed: %s", check_exc)
                    # 如果检查失败，可能页面已经跳转
                    return True

            # 最终检查
            try:
                still_visible = await page.locator('#waf_nc_block').is_visible(timeout=3000)
                return not still_visible
            except Exception:
                # 如果检查失败，假设滑块已经消失
                return True

        except Exception as exc:
            logger.info("[csair] slider solve attempt failed: %s", exc)
            return False

    async def _get_gap_position_by_image(self, page: Page, track_info: dict) -> float | None:
        """使用图像识别技术计算缺口位置。"""
        try:
            # 获取背景图的 URL
            bg_url = await page.evaluate(
                """() => {
                    const bgImg = document.querySelector('.nc_bg, #nc_1__scale_text, .nc_iconfont');
                    if (bgImg && bgImg.style && bgImg.style.backgroundImage) {
                        const match = bgImg.style.backgroundImage.match(/url\\(['"]?([^'"]+)['"]?\\)/);
                        return match ? match[1] : null;
                    }
                    return null;
                }"""
            )

            if not bg_url:
                return None

            logger.info("[csair] background image URL: %s", bg_url)

            # 尝试从 DOM 中获取缓存的数据
            gap_from_dom = await page.evaluate(
                """() => {
                    // 尝试从多个位置获取缺口信息
                    const candidates = [
                        window.nc_data,
                        window.nc,
                        document.querySelector('[data-gap-x]'),
                    ];

                    for (const c of candidates) {
                        if (!c) continue;
                        if (typeof c === 'object' && c.gap_x !== undefined) {
                            return c.gap_x;
                        }
                        if (c.dataset && c.dataset.gapX) {
                            return parseInt(c.dataset.gapX);
                        }
                    }
                    return null;
                }"""
            )

            if gap_from_dom is not None:
                return float(gap_from_dom)

            return None

        except Exception as exc:
            logger.info("[csair] gap position image recognition failed: %s", exc)
            return None

    async def _get_slider_track_info(self, page: Page) -> dict:
        """获取滑轨信息，包括宽度和缺口位置。"""
        try:
            return await page.evaluate(
                """() => {
                    const result = { width: 320, gap_x: null };

                    // 尝试获取滑轨宽度
                    const trackSelectors = [
                        '.nc_scale',
                        '.nc_1__scale_control',
                        '#nc_1__scale_control',
                        '.nc_scale_wrapper',
                    ];

                    for (const sel of trackSelectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0) {
                                result.width = rect.width;
                                break;
                            }
                        }
                    }

                    // 尝试获取缺口位置（阿里云可能存储在不同位置）
                    try {
                        if (window.nc) {
                            // 尝试获取 nc 对象中的信息
                            if (window.nc.c && window.nc.c.canvas) {
                                result.gap_x = window.nc.c.canvas.gapX || null;
                            }
                        }
                    } catch (e) {}

                    // 检查是否有其他存储的缺口数据
                    try {
                        const gapInfo = document.querySelector('.nc_gap');
                        if (gapInfo) {
                            const rect = gapInfo.getBoundingClientRect();
                            result.gap_x = rect.left;
                        }
                    } catch (e) {}

                    // 尝试从隐藏的 input 中获取
                    try {
                        const hiddenInput = document.querySelector('input[name="nc_token"]');
                        if (hiddenInput && hiddenInput.dataset) {
                            result.gap_x = hiddenInput.dataset.gapX || null;
                        }
                    } catch (e) {}

                    return result;
                }"""
            )
        except Exception as exc:
            logger.info("[csair] failed to get slider track info: %s", exc)
            return {'width': 320, 'gap_x': None}

    async def _get_slider_gap_position(self, page: Page) -> int | None:
        """尝试从页面获取滑块缺口位置（部分阿里云版本会提供）"""
        try:
            gap_info = await page.evaluate(
                """() => {
                    // 尝试从不同位置获取缺口信息
                    if (window.nc && window.nc.get_token) {
                        return null;
                    }
                    // 检查是否有存储的缺口数据
                    if (window.nc_data) {
                        return window.nc_data.gap_x || null;
                    }
                    return null;
                }"""
            )
            return gap_info
        except Exception:
            return None

    async def _slider_attempt_with_retry(
        self, page: Page, start_x: float, start_y: float, slide_distance: float
    ) -> bool:
        """单次滑块尝试，简化版快速滑动"""
        try:
            # 简化轨迹，只生成少量点
            points = _realistic_slide_points(start_x, start_y, slide_distance, steps=20)

            # 快速移动到起点并按下
            await page.mouse.move(start_x, start_y)
            await page.wait_for_timeout(50)
            await page.mouse.down()
            await page.wait_for_timeout(30)

            # 快速滑动
            for px, py in points:
                await page.mouse.move(px, py)
                await asyncio.sleep(0.01)

            # 松开
            await page.wait_for_timeout(50)
            await page.mouse.up()

            # 等待验证结果
            await page.wait_for_timeout(random.randint(1500, 2500))

            # 检查是否成功
            still_visible = await page.locator('#waf_nc_block').is_visible(timeout=2000)
            return not still_visible

        except Exception as exc:
            logger.info("[csair] slider attempt error: %s", exc)
            return False

            # 等待
            await page.wait_for_timeout(random.randint(150, 300))

            # 前进回到目标（可能略超过）
            forward_distance = backoff_distance + random.randint(3, 8)
            forward_points = _realistic_slide_points(
                backoff_points[-1][0], backoff_points[-1][1], forward_distance, steps=5
            )
            for px, py in forward_points:
                await page.mouse.move(px, py)
                await asyncio.sleep(random.uniform(0.010, 0.020))

            # 最终微调
            await page.wait_for_timeout(random.randint(100, 200))
            final_adjust = random.randint(-5, 5)
            if final_adjust != 0:
                adjust_points = _realistic_slide_points(
                    forward_points[-1][0], forward_points[-1][1], final_adjust, steps=3
                )
                for px, py in adjust_points:
                    await page.mouse.move(px, py)
                    await asyncio.sleep(random.uniform(0.008, 0.015))

            # 松开鼠标前的短暂停顿
            await page.wait_for_timeout(random.randint(150, 300))
            await page.mouse.up()

            # 等待验证结果
            await page.wait_for_timeout(random.randint(2500, 4500))

            # 检查是否成功
            still_visible = await page.locator('#waf_nc_block').is_visible(timeout=3000)
            return not still_visible

        except Exception as exc:
            logger.info("[csair] slider attempt error: %s", exc)
            return False

    async def close(self) -> None:
        """释放爬虫资源，并保存 cookies 以便下次使用。"""
        # 在关闭前保存 cookies
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


def _realistic_slide_points(
    start_x: float, start_y: float, distance: float, steps: int = 20
) -> list:
    """生成简单的滑块轨迹，确保到达目标位置。"""
    if distance < 0:
        distance = abs(distance)
        end_x = start_x - distance
    else:
        end_x = start_x + distance

    points = []
    for i in range(steps + 1):
        t = i / steps
        # 简单的缓动函数
        x = start_x + (end_x - start_x) * t
        # 小的垂直抖动
        y = start_y + random.uniform(-2, 2)
        points.append((x, y))

    # 确保最后一个点到达目标
    points[-1] = (end_x, start_y)
    return points


def _bezier_slide_points(
    start_x: float, start_y: float, distance: float, steps: int = 60
) -> list:
    """生成模拟人类拖动的贝塞尔曲线轨迹点（保留用于兼容）。"""
    # 控制点：加入随机抖动模拟手部不稳定
    cp1_x = start_x + distance * 0.3 + random.uniform(-5, 5)
    cp1_y = start_y + random.uniform(-8, 8)
    cp2_x = start_x + distance * 0.7 + random.uniform(-5, 5)
    cp2_y = start_y + random.uniform(-6, 6)
    end_x = start_x + distance
    end_y = start_y + random.uniform(-2, 2)

    points = []
    for i in range(steps + 1):
        t = i / steps
        # 三次贝塞尔公式
        x = ((1 - t) ** 3 * start_x
             + 3 * (1 - t) ** 2 * t * cp1_x
             + 3 * (1 - t) * t ** 2 * cp2_x
             + t ** 3 * end_x)
        y = ((1 - t) ** 3 * start_y
             + 3 * (1 - t) ** 2 * t * cp1_y
             + 3 * (1 - t) * t ** 2 * cp2_y
             + t ** 3 * end_y)
        points.append((x, y))
    return points
