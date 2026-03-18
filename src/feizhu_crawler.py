"""
飞猪爬虫模块
"""

import asyncio
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import date
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, ElementHandle
from src.base_crawler import FlightCrawler
from src.config import Route
from src.utils import retry_with_backoff
from src.exceptions import CrawlerError, NetworkError, TimeoutError, ParseError
import logging

logger = logging.getLogger(__name__)


# 飞猪城市代码映射
FEIZHU_CITY_MAP = {
    "北京": "PEK", "上海": "SHA", "广州": "CAN", "深圳": "SZX",
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


def get_feizhu_city_code(city_name: str) -> str:
    """获取飞猪城市代码"""
    return FEIZHU_CITY_MAP.get(city_name, city_name)


class FeizhuCrawler(FlightCrawler):
    """飞猪机票爬虫"""

    source = "feizhu"

    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.playwright = None

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def init(self) -> None:
        """初始化浏览器"""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=self.headless)
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            logger.info("飞猪浏览器初始化成功")
        except Exception as e:
            logger.error(f"飞猪浏览器初始化失败: {e}")
            raise CrawlerError(f"浏览器初始化失败: {e}")

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
                logger.error(f"[{self.source}] 搜索 {flight_date} 失败: {e}")
                continue

        return results

    async def _search_single_date(self, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        """搜索单日航班"""
        date_str = flight_date.strftime('%Y-%m-%d')
        url = self._build_search_url(route.from_city, route.to_city, date_str)

        try:
            response = await self.page.goto(url, wait_until='networkidle', timeout=30000)
            if not response or response.status != 200:
                raise NetworkError(f"页面加载失败: HTTP {response.status if response else 'None'}")

            logger.info(f"[{self.source}] 页面加载成功: {url}")

            await asyncio.sleep(2)

            flights = await self._parse_flights(route, flight_date)
            return flights
        except Exception as e:
            raise ParseError(f"解析失败: {e}")

    def _build_search_url(self, from_city: str, to_city: str, date_str: str) -> str:
        """构建搜索 URL"""
        from_code = get_feizhu_city_code(from_city)
        to_code = get_feizhu_city_code(to_city)
        return f"https://sjipiao.fliggy.com/flight_search_result.htm?spm=181.11358650.flight.dflightSearch1&tripType=0&depCity={from_code}&arrCity={to_code}&depDate={date_str}&depCityName=%E6%B7%B1%E5%9C%B3&arrCityName=%E4%B8%8A%E6%B5%B7&depDate={date_str}"

    async def _parse_flights(self, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        """解析航班列表"""
        flights = []
        items = []
        selectors = ['.flight-list-item', '.clearfix J_FlightItem']

        for selector in selectors:
            try:
                items = await self.page.query_selector_all(selector)
                if items:
                    logger.debug(f"[{self.source}] 使用选择器 {selector} 找到 {len(items)} 个航班")
                    break
            except Exception as e:
                logger.debug(f"[{self.source}] 选择器 {selector} 查询失败: {e}")
                continue

        for item in items:
            flight = await self._parse_single_flight(item, route, flight_date)
            if flight:
                flights.append(flight)

        logger.info(f"[{self.source}] 解析到 {len(flights)} 个航班")
        return flights

    async def _parse_single_flight(self, item: ElementHandle, route: Route, flight_date: date) -> Optional[Dict[str, Any]]:
        """解析单个航班"""
        try:
            # Flight number - [data-flight-no]
            flight_no = await self._get_text(item, ['[data-flight-no]'])

            # Airline - [data-airline]
            airline = await self._get_text(item, ['[data-airline]'])

            # Price - [data-price]
            price_elem = await item.query_selector('[data-price]')
            if price_elem:
                price_text = await price_elem.inner_text()
                price_match = re.search(r'¥(\d+)', price_text)
                if price_match:
                    price = int(price_match.group(1))
                else:
                    price = int(re.search(r'\d+', price_text).group(0))
            else:
                logger.debug(f"[{self.source}] 未找到价格元素")
                return None

            return {
                'flight_no': flight_no.strip(),
                'airline': airline.strip(),
                'price': price,
                'route_from': route.from_city,
                'route_to': route.to_city,
                'source': self.source
            }
        except Exception as e:
            logger.debug(f"[{self.source}] 解析航班失败: {e}")
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
            except Exception:
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
        except Exception:
            pass
