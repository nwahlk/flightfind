"""
携程爬虫模块
"""

import re
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import date, datetime
import glob
import sys
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, ElementHandle
from src.config import Route
from src.base_crawler import FlightCrawler
from src.exceptions import (
    CrawlerError, NetworkError, TimeoutError, ParseError,
    AntiBotError, BrowserCrashError
)
from src.utils import retry_with_backoff
import logging

logger = logging.getLogger(__name__)


# 已知航空公司代码 (用于航班号验证)
KNOWN_AIRLINES = [
    'MU',  # 东方航空
    'CA',  # 国际航空
    'CZ',  # 南方航空
    '3U',  # 四川航空
    'ZH',  # 深圳航空
    'HO',  # 吉祥航空
    'FM',  # 上海航空
    '9C',  # 春秋航空
    'KN',  # 联合航空
    'JD',  # 首都航空
    'NS',  # 河北航空
    '8L',  # 祥鹏航空
    'OQ',  # 重庆航空
    'TV',  # 西藏航空
    'GS',  # 天津航空
    'EU',  # 成都航空
    'DR',  # 北部湾航空
    'QW',  # 青岛航空
    'GT',  # 桂林航空
    'UQ',  # 乌鲁木齐航空
    'GX',  # 北部湾航空
    'RY',  # 瑞丽航空
    'YI',  # 英安航空
    'DZ',  # 东海航空
    'KY',  # 昆明航空
]


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


class CtripCrawler(FlightCrawler):
    """携程机票爬虫"""
    source = "ctrip"

    def __init__(self, headless: bool = True, debug_save_html: bool = False,
                 debug_html_path: Optional[Path] = None,
                 page_load_timeout: int = 45000):
        self.headless = headless
        self.debug_save_html = debug_save_html
        self.debug_html_path = debug_html_path or Path("./logs")
        self.page_load_timeout = page_load_timeout
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None

        # 确保日志目录存在
        if self.debug_save_html:
            self.debug_html_path.mkdir(parents=True, exist_ok=True)

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def init(self) -> None:
        """初始化浏览器"""
        try:
            self.playwright = await async_playwright().start()

            # 只保留必要参数，移除会暴露自动化特征的参数
            browser_args = [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--no-first-run',
                '--disable-blink-features=AutomationControlled',
            ]

            # 更真实的User-Agent
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

            # 跨平台查找本地安装的 Chromium/Chrome
            chrome_exe = self._find_local_chrome()

            launch_kwargs = dict(
                headless=self.headless,
                args=browser_args,
                slow_mo=100,
            )
            if chrome_exe and chrome_exe.exists():
                launch_kwargs["executable_path"] = str(chrome_exe)
                logger.info(f"使用本地 Chrome: {chrome_exe}")
            else:
                logger.info("本地 Chrome 未找到，使用 Playwright 内置浏览器")

            self.browser = await self.playwright.chromium.launch(**launch_kwargs)

            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=user_agent,
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
                ignore_https_errors=True,
                java_script_enabled=True,
            )

            # 注入脚本屏蔽 webdriver 特征
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
                window.chrome = { runtime: {} };
            """)

            logger.info("浏览器初始化成功")

        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            raise BrowserCrashError(f"浏览器初始化失败: {e}")

    def _find_local_chrome(self) -> Optional[Path]:
        """跨平台查找本地安装的 Chromium/Chrome"""
        home = Path.home()
        possible_paths = []

        # Windows - Playwright 安装的 Chromium
        windows_paths = list(home.glob("AppData/Local/ms-playwright/chromium-*/chrome-win64/chrome.exe"))
        possible_paths.extend(windows_paths)

        # Linux - Playwright 安装的 Chromium
        linux_paths = list(home.glob(".cache/ms-playwright/chromium-*/chrome-linux/chrome"))
        possible_paths.extend(linux_paths)

        # macOS - Playwright 安装的 Chromium
        mac_paths = list(home.glob("Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"))
        possible_paths.extend(mac_paths)

        # 返回最新版本（按路径排序，通常版本号在路径中）
        if possible_paths:
            # 按修改时间排序，取最新的
            possible_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return possible_paths[0]

        return None

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
            # 使用 networkidle 等页面 XHR 请求完成
            response = await self.page.goto(url, wait_until='networkidle', timeout=self.page_load_timeout)

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

            # 等待骨架屏消失、真实航班卡片出现
            try:
                await self.page.wait_for_selector(
                    '.flight-box, .flight-item',
                    timeout=30000
                )
                logger.info("找到航班列表元素")
            except:
                logger.warning("未找到航班列表选择器，尝试继续解析")

            await asyncio.sleep(1)

            # 保存页面 HTML 供调试 (使用时间戳避免覆盖)
            if self.debug_save_html:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"ctrip_debug_{route.from_city}_{route.to_city}_{date_str}_{timestamp}.html"
                debug_file = self.debug_html_path / filename
                html = await self.page.content()
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(html)
                logger.info(f"已保存页面 HTML 到 {debug_file}")

            flights = await self._parse_flights(route, flight_date)
            return flights

        except Exception as e:
            if isinstance(e, (AntiBotError, NetworkError, TimeoutError)):
                raise
            raise ParseError(f"解析失败: {e}")

    def _build_search_url(self, from_city: str, to_city: str, date_str: str) -> str:
        """构建搜索 URL"""
        from_code = get_city_code(from_city)
        to_code = get_city_code(to_city)
        return f"https://flights.ctrip.com/itinerary/oneway/{from_code}-{to_code}?depdate={date_str}&adult=1&child=0&infant=0"

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

        # 使用Ctrip itinerary页面的实际选择器
        selectors = [
            '.flight-box',     # itinerary 页面的航班卡片
            '.flight-item',
            '[class*="flightItem"]',
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
            # 航班号 - 实际 class 为 .plane-No
            flight_no_raw = await self._get_text(item, [
                '.plane-No', '.flight-no', '.flight-number',
                '[class*="plane-No"]', '[class*="flight-no"]'
            ])
            # plane-No 文本如 "MU5358 空客321-200(中)"，只取航班号部分
            # 严格匹配 2-3位字母 + 3-4位数字 的航班号格式
            flight_no = 'Unknown'
            if flight_no_raw:
                flight_no_match = re.search(r'([A-Z]{2,3}\d{3,4})', flight_no_raw.strip())
                if flight_no_match:
                    candidate = flight_no_match.group(1)
                    # 验证航空公司代码是否在已知列表中
                    airline_code = candidate[:2]
                    if airline_code in KNOWN_AIRLINES:
                        flight_no = candidate
                    else:
                        logger.debug(f"未知航空公司代码 {airline_code}，航班号: {candidate}")

            # 航空公司
            airline_raw = await self._get_text(item, [
                '.airline-name', '.airline', '.company-name',
                '[class*="airline"]', '[class*="company"]'
            ])
            # 去掉混入的航班号和机型，如 "深圳航空ZH9327\xa0空客320(中)" → "深圳航空"
            # 使用更精确的正则表达式
            airline = airline_raw.strip() if airline_raw else 'Unknown'
            if airline != 'Unknown':
                # 先尝试移除航班号和机型信息
                airline = re.sub(r'[A-Z]{2,3}\d{3,4}', '', airline)  # 移除航班号
                airline = re.sub(r'空客\d+.*?\(.*?\)', '', airline)  # 移除机型信息
                airline = re.sub(r'波音\d+.*?\(.*?\)', '', airline)  # 移除机型信息
                airline = airline.strip('\xa0 　\n\r')
                if not airline:
                    airline = airline_raw.strip()

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
                'route_from': route.from_city,
                'route_to': route.to_city,
                'source': self.source
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
