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
from src.city_codes import COMMON_CITY_CODE_MAP
from src.config import Route
from src.exceptions import BrowserCrashError, CrawlerError, ParseError
from src.flight_record import normalize_flight_record
from src.utils import retry_with_backoff

logger = logging.getLogger(__name__)


# 携程城市代码映射（使用共享映射）
CTRIP_CITY_CODE_MAP = COMMON_CITY_CODE_MAP


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

            # 先保存调试快照，便于调试
            await self._save_debug_snapshot(page, route, flight_date, "page")

            # 解析航班
            flights = await self._parse_flights(page, route, flight_date)

            if not flights:
                raise ParseError("ctrip page did not yield any flights")

            return flights

        finally:
            await page.close()

    async def _check_antibot(self, page: Page) -> bool:
        """检查是否有风控"""
        try:
            title = await page.title()
            url = page.url

            # 只检查页面标题和URL，不检查body（body可能包含脚本引用导致误报）
            # 真正的风控页面标题通常会包含这些关键词
            title_signals = ["验证", "captcha", "拦截", "禁止访问", "Too Many Requests", "访问频繁", "安全验证"]
            title_haystack = f"{title}\n{url}"

            if any(signal.lower() in title_haystack.lower() for signal in title_signals):
                return True

            # 检查是否有可见的验证码元素（滑块、图形验证等）
            captcha_selectors = [
                ".captcha-container",
                "[class*='captcha']",
                "[class*='slider-verify']",
                ".nc_wrapper",  # 阿里云滑块验证
                "#nc_1_wrapper",
            ]
            for selector in captcha_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            return True
                except Exception:
                    continue

            return False
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
        # 携程航班项选择器（2024年新版页面结构）
        # 注意：携程使用 React 动态渲染，需要等待元素出现
        selectors = [
            "[class*='flight-item']",
            "[class*='FlightItem']",
            "[class*='list-item']",
            "[class*='ListItem']",
            ".flight-row",
            "[data-flight]",
        ]

        # 等待航班列表加载
        try:
            await page.wait_for_selector("[class*='flight'], [class*='Flight']", timeout=10000)
        except Exception:
            pass

        # 使用 JavaScript 直接从渲染后的 DOM 中提取航班数据
        # 携程使用 React 渲染，需要从 DOM 元素和属性中提取
        flight_data = await page.evaluate(r'''() => {
            const results = [];
            const debugInfo = { prices: [], times: [], flightNos: [], rawHtml: [] };

            // 方法1: 遍历所有元素，查找包含航班信息的元素
            const allElements = document.querySelectorAll('*');
            for (const el of allElements) {
                const text = el.innerText || '';
                const className = el.className || '';
                const id = el.id || '';

                // 检查 aria-label 和 title 属性
                const ariaLabel = el.getAttribute('aria-label') || '';
                const title = el.getAttribute('title') || '';
                const dataAttrs = el.dataset || {};

                // 查找航班号（可能在 aria-label 或其他属性中）
                const flightNoMatch = (ariaLabel + ' ' + title).match(/[A-Z]{2}\d{3,4}/);
                if (flightNoMatch) {
                    debugInfo.flightNos.push({
                        flightNo: flightNoMatch[0],
                        source: 'attr',
                        context: ariaLabel || title
                    });
                }

                // 收集价格信息
                if (/¥|￥/.test(text) && /\d{3,4}/.test(text) && text.length < 50) {
                    debugInfo.prices.push(text.trim());
                }

                // 收集时间信息
                if (/\d{2}:\d{2}/.test(text) && text.length < 30) {
                    debugInfo.times.push(text.trim());
                }
            }

            // 方法2: 从页面 HTML 中提取航班号
            const html = document.body.innerHTML;
            const flightNoInHtml = html.match(/[A-Z]{2}\d{3,4}/g) || [];
            debugInfo.flightNosFromHtml = [...new Set(flightNoInHtml)].slice(0, 20);

            // 方法3: 查找航班卡片容器
            const cardSelectors = [
                '[class*="flight-card"]',
                '[class*="FlightCard"]',
                '[class*="list-item"]',
                '[data-flight]'
            ];

            for (const selector of cardSelectors) {
                const cards = document.querySelectorAll(selector);
                if (cards.length > 0) {
                    debugInfo.rawHtml.push(`Found ${cards.length} cards via ${selector}`);
                    for (const card of Array.from(cards).slice(0, 3)) {
                        debugInfo.rawHtml.push(card.outerHTML.substring(0, 300));
                    }
                }
            }

            return debugInfo;
        }''')

        # 提取调试信息
        flight_nos = flight_data.get("flightNos", [])
        flight_nos_html = flight_data.get("flightNosFromHtml", [])
        prices = flight_data.get("prices", [])
        times = flight_data.get("times", [])
        raw_html = flight_data.get("rawHtml", [])

        logger.info("[ctrip] found %d flightNos in attrs, %d in HTML, %d prices, %d times",
                    len(flight_nos), len(flight_nos_html), len(prices), len(times))

        # 调试输出
        if flight_nos:
            logger.debug("[ctrip] flight numbers from attrs: %s", flight_nos[:5])
        if flight_nos_html:
            logger.debug("[ctrip] flight numbers from HTML: %s", flight_nos_html[:10])
        if prices:
            logger.debug("[ctrip] prices: %s", prices[:5])
        if times:
            logger.debug("[ctrip] times: %s", times[:5])
        if raw_html:
            logger.debug("[ctrip] card info: %s", raw_html[:3])

        # 如果 HTML 中有航班号，说明页面有数据，只是解析问题
        if not flight_nos_html:
            logger.warning("[ctrip] no flight numbers found in page HTML - possible anti-bot or loading issue")

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

        if flight_nos_html and prices:
            price_values = []
            for p in prices:
                matches = re.findall(r'(\d{3,4})', p)
                for m in matches:
                    price_values.append(int(m))

            unique_prices = sorted(set(price_values))
            logger.info("[ctrip] extracted %d unique prices: %s", len(unique_prices), unique_prices[:10])

            # 过滤有效的航班号（标准航空公司代码）
            valid_airline_codes = {
                'MU', 'CA', 'CZ', 'HU', 'ZH', 'FM', 'MF', 'SC', '3U', 'HO',
                '9C', 'GS', 'PN', 'G5', 'JR', 'EU', 'AQ', 'RY', 'GT', 'GX',
                'DR', 'QW', 'A6', 'Y8', 'DZ', 'OQ', 'CN', 'KN', 'NS', 'JD',
                'GJ', 'FU', 'TV', 'UQ', 'CK', 'PO', 'O3', 'VD', '8L', 'YI'
            }

            valid_flight_nos = [
                fn for fn in flight_nos_html
                if fn[:2] in valid_airline_codes
            ]

            logger.info("[ctrip] filtered %d valid flight numbers from %d",
                        len(valid_flight_nos), len(flight_nos_html))

            # 为每个有效航班号创建航班记录
            for i, flight_no in enumerate(valid_flight_nos):
                if i < len(unique_prices):
                    price = unique_prices[i]
                else:
                    price = unique_prices[-1] if unique_prices else 500

                # 推断航空公司
                airline = self._guess_airline(flight_no)

                flight = normalize_flight_record(
                    route_from=route.from_city,
                    route_to=route.to_city,
                    flight_date=flight_date,
                    flight_no=flight_no,
                    airline=airline,
                    price=price,
                    source=self.source,
                    departure_airport="",
                    arrival_airport="",
                    metadata={
                        "record_type": "extracted_from_html",
                    },
                )
                key = (flight["flight_no"], flight["price"])
                if key not in seen:
                    seen.add(key)
                    flights.append(flight)

        # 如果上面方法失败，回退到元素解析
        if not flights and items:
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

    def _parse_flight_text(self, text: str, route: Route, flight_date: date) -> Dict[str, Any] | None:
        """从文本中解析航班信息"""
        try:
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
