# src/base_crawler.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from src.config import Route

class FlightCrawler(ABC):
    """航班爬虫抽象基类"""

    source: str  # Each crawler must define its source name

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None

    @abstractmethod
    async def init(self) -> None:
        """初始化浏览器和资源"""

    @abstractmethod
    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        """搜索航班，返回标准格式数据"""

    @abstractmethod
    async def close(self) -> None:
        """清理资源"""
