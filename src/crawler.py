"""
携程爬虫模块
"""

import re
import asyncio
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, ElementHandle
from src.config import Route
from src.exceptions import (
    CrawlerError, NetworkError, TimeoutError, ParseError,
    AntiBotError, BrowserCrashError
)
from src.utils import retry_with_backoff
import logging

logger = logging.getLogger(__name__)


# 城市到机场代码映射
CITY_CODE_MAP = {
    # 主要城市
    "北京": "BJS", "上海": "SHA", "广州": "CAN", "深圳": "SZX",
    "成都": "CTU", "杭州": "HGH", "西安": "XIY", "重庆": "CKG",
    "南京": "NKG", "武汉": "WUH", "天津": "TSN", "青岛": "TAO",
    "大连": "DLC", "厦门": "XMN", "昆明": "KMG", "长沙": "CSX",
    "郑州": "CGO", "沈阳": "SHE", "济南": "TNA", "哈尔滨": "HRB",
    "三亚": "SYX", "海口": "HAK", "福州": "FOC", "南宁": "NNG",
    "贵阳": "KWE", "兰州": "LHW", "银川": "INC", "西宁": "XNN",
    "拉萨": "LXA", "乌鲁木齐": "URC", "呼和浩特": "HET", "石家庄": "SJW",
    "太原": "TYN", "长春": "CGQ", "温州": "WNZ", "宁波": "NGB",
    "合肥": "HFE", "南昌": "KHN", "桂林": "KWL", "丽江": "LJG",
}


def get_city_code(city_name: str) -> str:
    """获取城市对应的机场代码"""
    return CITY_CODE_MAP.get(city_name, city_name)


class CtripCrawler:
    """携程机票爬虫"""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def init(self) -> None:
        """初始化浏览器"""
        try:
            self.playwright = await async_playwright().start()

            # 更多的浏览器参数来绕过反爬检测和防止崩溃
            browser_args = [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--no-first-run',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--window-size=1920,1080',
                '--disable-extensions',
            ]

            # 更真实的User-Agent
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=browser_args,
                slow_mo=50  # 添加一点延迟，模拟人类操作
            )

            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=user_agent,
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
                # 添加一些额外的选项
                ignore_https_errors=True,
                java_script_enabled=True,
            )

            logger.info("浏览器初始化成功")

        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            raise BrowserCrashError(f"浏览器初始化失败: {e}")

    @retry_with_backoff(max_attempts=3, base_delay=5.0)
    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        """搜索航班"""
        if not self.page:
            self.page = await self.context.new_page()

        results = []

        for flight_date in route.dates.absolute_dates:
            try:
                flights = await self._search_single_date(route, flight_date)
                results.extend(flights)
            except Exception as e:
                logger.error(f"搜索 {flight_date} 失败: {e}")
                raise CrawlerError(f"搜索 {flight_date} 失败: {e}")

        return results

    async def _search_single_date(self, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        """搜索单日航班"""
        date_str = flight_date.strftime('%Y-%m-%d')
        url = self._build_search_url(route.from_city, route.to_city, date_str)

        try:
            # 使用 domcontentloaded 而不是 networkidle，避免超时
            response = await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)

            if not response or response.status != 200:
                raise NetworkError(f"页面加载失败: HTTP {response.status if response else 'None'}")

            logger.info(f"页面加载成功: {url}")

            if await self._detect_anti_bot():
                raise AntiBotError("检测到反爬验证")

            # 等待航班列表加载（使用Ctrip实际的选择器）
            # 先尝试等待主要内容区域
            try:
                await self.page.wait_for_selector('body', timeout=5000)
            except:
                pass

            # 等待航班列表元素出现
            try:
                await self.page.wait_for_selector(
                    '.low-price-flights-bd, .low-price-flights-route-item, [class*="flight"]',
                    timeout=20000
                )
                logger.info("找到航班列表元素")
            except:
                # 如果选择器未找到，可能是页面结构不同或被阻止
                logger.warning("未找到航班列表选择器，尝试继续解析")

            # 额外等待，确保动态内容加载完成
            await asyncio.sleep(3)

            flights = await self._parse_flights(route, flight_date)
            return flights

        except Exception as e:
            if isinstance(e, (AntiBotError, NetworkError, TimeoutError)):
                raise
            raise ParseError(f"解析失败: {e}")

    def _build_search_url(self, from_city: str, to_city: str, date_str: str) -> str:
        """构建搜索 URL"""
        # 使用机场代码
        from_code = get_city_code(from_city)
        to_code = get_city_code(to_city)
        return f"https://flights.ctrip.com/online/channel/domestic?from={from_code}&to={to_code}&depart={date_str}"

    async def _detect_anti_bot(self) -> bool:
        """检测反爬"""
        selectors = [
            '.captcha', '#captcha', '.slider', '.verify-code', '[class*="anti"]'
        ]

        for selector in selectors:
            try:
                element = await self.page.query_selector(selector)
                if element and await element.is_visible():
                    return True
            except:
                continue

        try:
            text = await self.page.inner_text('body')
            keywords = ['验证码', '请验证', '安全验证', '滑动验证']
            for kw in keywords:
                if kw in text:
                    return True
        except:
            pass

        return False

    async def _parse_flights(self, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        """解析航班列表"""
        flights = []

        # 使用Ctrip实际的选择器（按优先级排序）
        selectors = [
            '.low-price-flights-route-item',      # 低价航班列表项
            '.flight-item',                        # 通用航班项
            '[class*="flight"]',                # 包含flight的类名
        ]

        items = []
        for selector in selectors:
            items = await self.page.query_selector_all(selector)
            if items:
                logger.info(f"使用选择器找到 {len(items)} 个航班元素: {selector}")
                break

        logger.info(f"解析到 {len(items)} 个航班项")

        for item in items:
            try:
                flight = await self._parse_single_flight(item, route, flight_date)
                if flight:
                    flights.append(flight)
            except Exception as e:
                logger.debug(f"解析单个航班失败: {e}")
                continue

        return flights

    async def _parse_single_flight(
        self, item: ElementHandle, route: Route, flight_date: date
    ) -> Optional[Dict[str, Any]]:
        """解析单个航班"""
        try:
            # 航班号 - Ctrip可能使用不同的元素
            flight_no = await self._get_text(item, [
                '.flight-no', '.flight-number', '.low-price-flights-route-flight',
                '[class*="flight-no"]', '[class*="flightnumber"]'
            ])

            # 航空公司
            airline = await self._get_text(item, [
                '.airline-name', '.airline', '.company-name',
                '[class*="airline"]', '[class*="company"]'
            ])

            # 价格 - Ctrip实际使用的价格选择器
            price_text = await self._get_text(item, [
                '.low-price-flights-route-flight-price',  # Ctrip低价航班价格
                '.price', '.amount', '[class*="price"]'
            ])

            # 从价格文本中提取数字
            price_match = re.search(r'\d+', price_text)
            if not price_match:
                logger.debug(f"无法从文本中提取价格: {price_text}")
                return None
            price = int(price_match.group())

            # 如果价格为0或太小，可能不是有效价格
            if price < 10:
                return None

            return {
                'flight_no': flight_no.strip() if flight_no else 'Unknown',
                'airline': airline.strip() if airline else 'Unknown',
                'price': price,
                'date': flight_date.isoformat(),
                'route_from': route.from_city,
                'route_to': route.to_city
            }

        except Exception as e:
            logger.debug(f"解析航班失败: {e}")
            return None

    async def _get_text(self, item: ElementHandle, selectors: list) -> str:
        """尝试多个选择器获取文本"""
        for selector in selectors:
            try:
                elem = await item.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if text:
                        return text.strip()
            except:
                continue
        return ""

    async def close(self) -> None:
        """关闭浏览器"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            pass
