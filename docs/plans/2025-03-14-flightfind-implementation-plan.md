# FlightFind 机票监控工具 - 实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个本地运行的携程机票价格监控工具，支持多航线监控、多渠道通知、价格历史记录。

**Architecture:** 使用 Playwright 模拟浏览器访问携程，APScheduler 定时调度任务，SQLite 存储价格历史，异步通知模块支持邮件/Webhook/Bark推送。

**Tech Stack:** Python 3.9+, Playwright, APScheduler, aiosqlite, Pydantic, PyYAML

---

## 项目结构

```
flightfind/
├── config.yaml              # 用户配置文件
├── config.example.yaml      # 配置模板
├── main.py                  # 主程序入口
├── requirements.txt         # Python 依赖
├── README.md               # 项目说明
├── docs/
│   ├── specs/
│   │   └── 2025-03-14-flightfind-design.md  # 设计文档
│   └── plans/
│       └── 2025-03-14-flightfind-implementation-plan.md  # 本文件
├── src/
│   ├── __init__.py
│   ├── config.py          # 配置加载与验证
│   ├── database.py        # 数据库操作
│   ├── crawler.py         # 爬虫逻辑
│   ├── parser.py          # 价格解析
│   ├── notifier.py        # 通知发送
│   ├── scheduler.py       # 调度管理
│   ├── exceptions.py      # 异常定义
│   └── utils.py           # 工具函数
├── data/
│   └── flights.db         # SQLite 数据库（自动创建）
└── logs/
    └── monitor.log        # 运行日志（自动创建）
```

---

## 依赖清单

**requirements.txt:**

```
# 核心依赖
playwright>=1.40.0
APScheduler>=3.10.0
aiosqlite>=0.19.0
pydantic>=2.0.0
PyYAML>=6.0.0

# 网络请求
aiohttp>=3.9.0

# 日志
python-json-logger>=2.0.0

# 开发依赖（可选）
pytest>=7.0.0
pytest-asyncio>=0.21.0
black>=23.0.0
```

---

## Task 1: 项目基础结构

**Files:**
- Create: `requirements.txt`
- Create: `config.example.yaml`
- Create: `src/__init__.py`
- Create: `src/exceptions.py`

### Step 1: Create requirements.txt

```txt
# 核心依赖
playwright>=1.40.0
APScheduler>=3.10.0
aiosqlite>=0.19.0
pydantic>=2.0.0
PyYAML>=6.0.0

# 网络请求
aiohttp>=3.9.0

# 日志
python-json-logger>=2.0.0

# 开发依赖（可选）
pytest>=7.0.0
pytest-asyncio>=0.21.0
black>=23.0.0
```

### Step 2: Create config.example.yaml

```yaml
# FlightFind 机票监控配置示例

monitor:
  check_interval: 30  # 检查间隔，单位：分钟
  headless: true      # true=无界面运行，false=显示浏览器窗口（调试用）

routes:
  - from: "深圳"
    to: "上海"
    low_price_threshold: 600
    dates:
      mode: "absolute"
      absolute_dates: ["2025-04-01", "2025-04-02", "2025-04-03"]

  - from: "上海"
    to: "深圳"
    low_price_threshold: 800
    dates:
      mode: "absolute"
      absolute_dates: ["2025-04-05", "2025-04-10", "2025-04-15"]

default_dates:
  mode: "absolute"
  absolute_dates: []

notifications:
  email:
    enabled: true
    smtp_server: "smtp.qq.com"
    smtp_port: 465
    username: "your_email@qq.com"
    password: "your_auth_code"
    to: ["your_email@qq.com"]

  webhook:
    enabled: false
    url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx"

  bark:
    enabled: false
    device_key: "your_device_key"
    server: "https://api.day.app"
```

### Step 3: Create src/exceptions.py

```python
"""
FlightFind 异常定义
"""


class FlightFindError(Exception):
    """基础异常"""
    pass


class ConfigError(FlightFindError):
    """配置错误"""
    pass


class DatabaseError(FlightFindError):
    """数据库错误"""
    pass


class CrawlerError(FlightFindError):
    """爬虫错误"""
    pass


class NetworkError(CrawlerError):
    """网络错误"""
    pass


class TimeoutError(CrawlerError):
    """超时错误"""
    pass


class ParseError(CrawlerError):
    """解析错误"""
    pass


class AntiBotError(CrawlerError):
    """反爬检测"""
    pass


class NotifierError(FlightFindError):
    """通知错误"""
    pass


class RetryExhaustedError(FlightFindError):
    """重试耗尽"""
    pass
```

---

## Task 2: 配置管理模块

**Files:**
- Create: `src/config.py`
- Create: `src/utils.py`

### Step 1: Create src/utils.py

```python
"""
工具函数
"""

import logging
import sys
from pathlib import Path


def setup_logging(log_file: Path = None, level: int = logging.INFO) -> logging.Logger:
    """配置日志"""
    logger = logging.getLogger("flightfind")
    logger.setLevel(level)

    # 清除已有处理器
    logger.handlers.clear()

    # 格式化
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件输出
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def retry_with_backoff(max_attempts: int = 3, base_delay: float = 1.0):
    """重试装饰器"""
    def decorator(func):
        import asyncio
        import random

        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    delay = base_delay * (2 ** attempt) + random.random()
                    await asyncio.sleep(delay)
            return None
        return wrapper
    return decorator
```

### Step 2: Create src/config.py

```python
"""
配置管理模块
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union
import yaml
from src.exceptions import ConfigError


@dataclass
class DateConfig:
    """日期配置"""
    mode: Literal["absolute", "relative"] = "absolute"
    absolute_dates: List[date] = field(default_factory=list)
    relative_days: List[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "DateConfig":
        if not data:
            return cls()

        mode = data.get("mode", "absolute")

        if mode == "absolute":
            date_strings = data.get("absolute_dates", [])
            dates = []
            for d in date_strings:
                if isinstance(d, str):
                    dates.append(date.fromisoformat(d))
                elif isinstance(d, date):
                    dates.append(d)
            return cls(mode=mode, absolute_dates=dates)
        else:
            return cls(
                mode=mode,
                relative_days=data.get("relative_days", [])
            )


@dataclass
class Route:
    """航线配置"""
    from_city: str
    to_city: str
    low_price_threshold: int
    dates: DateConfig

    @classmethod
    def from_dict(cls, data: dict) -> "Route":
        return cls(
            from_city=data["from"],
            to_city=data["to"],
            low_price_threshold=data["low_price_threshold"],
            dates=DateConfig.from_dict(data.get("dates", {}))
        )


@dataclass
class EmailConfig:
    """邮件配置"""
    enabled: bool = False
    smtp_server: str = ""
    smtp_port: int = 465
    username: str = ""
    password: str = ""
    to: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "EmailConfig":
        return cls(
            enabled=data.get("enabled", False),
            smtp_server=data.get("smtp_server", ""),
            smtp_port=data.get("smtp_port", 465),
            username=data.get("username", ""),
            password=data.get("password", ""),
            to=data.get("to", [])
        )


@dataclass
class WebhookConfig:
    """Webhook配置"""
    enabled: bool = False
    url: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "WebhookConfig":
        return cls(
            enabled=data.get("enabled", False),
            url=data.get("url", "")
        )


@dataclass
class BarkConfig:
    """Bark配置"""
    enabled: bool = False
    device_key: str = ""
    server: str = "https://api.day.app"

    @classmethod
    def from_dict(cls, data: dict) -> "BarkConfig":
        return cls(
            enabled=data.get("enabled", False),
            device_key=data.get("device_key", ""),
            server=data.get("server", "https://api.day.app")
        )


@dataclass
class MonitorConfig:
    """监控配置"""
    check_interval: int = 30
    headless: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "MonitorConfig":
        return cls(
            check_interval=data.get("check_interval", 30),
            headless=data.get("headless", True)
        )


@dataclass
class NotificationsConfig:
    """通知配置"""
    email: EmailConfig
    webhook: WebhookConfig
    bark: BarkConfig

    @classmethod
    def from_dict(cls, data: dict) -> "NotificationsConfig":
        return cls(
            email=EmailConfig.from_dict(data.get("email", {})),
            webhook=WebhookConfig.from_dict(data.get("webhook", {})),
            bark=BarkConfig.from_dict(data.get("bark", {}))
        )


@dataclass
class AppConfig:
    """应用完整配置"""
    monitor: MonitorConfig
    routes: List[Route]
    default_dates: DateConfig
    notifications: NotificationsConfig

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        return cls(
            monitor=MonitorConfig.from_dict(data.get("monitor", {})),
            routes=[Route.from_dict(r) for r in data.get("routes", [])],
            default_dates=DateConfig.from_dict(data.get("default_dates", {})),
            notifications=NotificationsConfig.from_dict(data.get("notifications", {}))
        )


def load_config(config_path: Union[str, Path]) -> AppConfig:
    """
    加载配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        AppConfig 实例

    Raises:
        ConfigError: 配置文件不存在或格式错误
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise ConfigError(f"配置文件不存在: {config_path}")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data:
            raise ConfigError("配置文件为空")

        config = AppConfig.from_dict(data)

        # 验证配置
        _validate_config(config)

        return config

    except yaml.YAMLError as e:
        raise ConfigError(f"配置文件格式错误: {e}")
    except Exception as e:
        if isinstance(e, ConfigError):
            raise
        raise ConfigError(f"加载配置失败: {e}")


def _validate_config(config: AppConfig) -> None:
    """验证配置有效性"""
    if not config.routes:
        raise ConfigError("至少配置一条航线")

    for i, route in enumerate(config.routes):
        if not route.from_city or not route.to_city:
            raise ConfigError(f"航线 {i+1}: 出发地和目的地不能为空")

        if route.low_price_threshold <= 0:
            raise ConfigError(f"航线 {i+1}: 价格阈值必须大于0")

        if not route.dates.absolute_dates and not route.dates.relative_days:
            raise ConfigError(f"航线 {i+1}: 必须配置至少一个日期")

    # 检查至少启用了一个通知渠道
    has_notification = (
        config.notifications.email.enabled or
        config.notifications.webhook.enabled or
        config.notifications.bark.enabled
    )

    if not has_notification:
        raise ConfigError("至少启用一个通知渠道")
```

---

## Task 3: 数据库模块

**Files:**
- Create: `src/database.py`

### Step 1: 实现数据库接口

```python
"""
数据库模块
"""

import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import aiosqlite
from src.exceptions import DatabaseError


class Database:
    """SQLite 数据库管理器"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        """初始化数据库（创建表）"""
        async with self._get_connection() as db:
            await db.executescript(self._get_schema())
            await db.commit()

    @asynccontextmanager
    async def _get_connection(self):
        """获取数据库连接"""
        db = None
        try:
            db = await aiosqlite.connect(self.db_path)
            db.row_factory = aiosqlite.Row
            yield db
        finally:
            if db:
                await db.close()

    def _get_schema(self) -> str:
        """获取数据库Schema"""
        return '''
        -- 价格历史记录表
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_from TEXT NOT NULL,
            route_to TEXT NOT NULL,
            flight_date DATE NOT NULL,
            flight_no TEXT,
            airline TEXT,
            price INTEGER NOT NULL,
            check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_price_route ON price_history(route_from, route_to);
        CREATE INDEX IF NOT EXISTS idx_price_date ON price_history(flight_date);

        -- 低价提醒记录表
        CREATE TABLE IF NOT EXISTS low_price_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_from TEXT NOT NULL,
            route_to TEXT NOT NULL,
            flight_date DATE NOT NULL,
            flight_no TEXT,
            airline TEXT,
            price INTEGER NOT NULL,
            threshold INTEGER NOT NULL,
            alert_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notified BOOLEAN DEFAULT FALSE,
            notification_channels TEXT
        );

        -- 执行日志表
        CREATE TABLE IF NOT EXISTS execution_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            route_from TEXT,
            route_to TEXT,
            flight_date TEXT,
            status TEXT NOT NULL,
            message TEXT,
            execution_time_ms INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        '''

    async def save_price_history(
        self,
        route_from: str,
        route_to: str,
        flight_date: date,
        flight_no: str,
        airline: str,
        price: int
    ) -> None:
        """保存价格历史"""
        async with self._get_connection() as db:
            await db.execute('''
                INSERT INTO price_history
                (route_from, route_to, flight_date, flight_no, airline, price)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (route_from, route_to, flight_date, flight_no, airline, price))
            await db.commit()

    async def save_alert(
        self,
        route_from: str,
        route_to: str,
        flight_date: date,
        flight_no: str,
        airline: str,
        price: int,
        threshold: int,
        channels: List[str]
    ) -> None:
        """保存低价提醒"""
        async with self._get_connection() as db:
            await db.execute('''
                INSERT INTO low_price_alerts
                (route_from, route_to, flight_date, flight_no, airline, price, threshold, notification_channels)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                route_from, route_to, flight_date, flight_no, airline,
                price, threshold, ','.join(channels)
            ))
            await db.commit()

    async def log_execution(
        self,
        job_id: str,
        route_from: Optional[str],
        route_to: Optional[str],
        flight_date: Optional[str],
        status: str,
        message: Optional[str] = None,
        execution_time_ms: Optional[int] = None
    ) -> None:
        """记录执行日志"""
        async with self._get_connection() as db:
            await db.execute('''
                INSERT INTO execution_logs
                (job_id, route_from, route_to, flight_date, status, message, execution_time_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (job_id, route_from, route_to, flight_date, status, message, execution_time_ms))
            await db.commit()
```

---

## Task 4: 爬虫模块

**Files:**
- Create: `src/crawler.py`
- Create: `src/parser.py`

### Step 1: Create src/crawler.py

```python
"""
携程爬虫模块
"""

import re
import asyncio
from typing import List, Optional
from datetime import datetime
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, ElementHandle
from src.config import Route, DateConfig
from src.exceptions import (
    CrawlerError, NetworkError, TimeoutError, ParseError,
    AntiBotError, BrowserCrashError
)
from src.utils import retry_with_backoff


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

            browser_args = [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--no-first-run',
            ]

            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=browser_args
            )

            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0',
                locale='zh-CN',
                timezone_id='Asia/Shanghai'
            )

        except Exception as e:
            raise BrowserCrashError(f"浏览器初始化失败: {e}")

    @retry_with_backoff(max_attempts=3, base_delay=5.0)
    async def search_flights(self, route: Route) -> List[dict]:
        """
        搜索航班

        Returns:
            List[dict]: 航班列表，每个字典包含:
                - flight_no: 航班号
                - airline: 航空公司
                - price: 价格
                - date: 日期
        """
        if not self.page:
            self.page = await self.context.new_page()

        results = []

        for flight_date in route.dates.absolute_dates:
            try:
                flights = await self._search_single_date(route, flight_date)
                results.extend(flights)
            except Exception as e:
                raise CrawlerError(f"搜索 {flight_date} 失败: {e}")

        return results

    async def _search_single_date(self, route: Route, flight_date: date) -> List[dict]:
        """搜索单日航班"""
        date_str = flight_date.strftime('%Y-%m-%d')

        # 构建搜索 URL
        url = self._build_search_url(route.from_city, route.to_city, date_str)

        try:
            response = await self.page.goto(url, wait_until='networkidle', timeout=30000)

            if not response or response.status != 200:
                raise NetworkError(f"页面加载失败: HTTP {response.status if response else 'None'}")

            # 检查反爬
            if await self._detect_anti_bot():
                raise AntiBotError("检测到反爬验证")

            # 等待航班列表
            await self.page.wait_for_selector(
                '.flight-item, .flight-list-item, .flight-card',
                timeout=15000
            )

            # 解析航班
            flights = await self._parse_flights(route, flight_date)

            return flights

        except Exception as e:
            if isinstance(e, (AntiBotError, NetworkError, TimeoutError)):
                raise
            raise ParseError(f"解析失败: {e}")

    def _build_search_url(self, from_city: str, to_city: str, date_str: str) -> str:
        """构建搜索 URL"""
        # 简化版本，实际应该映射城市名到代码
        return f"https://flights.ctrip.com/online/channel/domestic?from={from_city}&to={to_city}&depart={date_str}"

    async def _detect_anti_bot(self) -> bool:
        """检测反爬"""
        selectors = [
            '.captcha',
            '#captcha',
            '.slider',
            '.verify-code',
            '[class*="anti"]'
        ]

        for selector in selectors:
            try:
                element = await self.page.query_selector(selector)
                if element and await element.is_visible():
                    return True
            except:
                continue

        # 检查页面文字
        try:
            text = await self.page.inner_text('body')
            keywords = ['验证码', '请验证', '安全验证', '滑动验证']
            for kw in keywords:
                if kw in text:
                    return True
        except:
            pass

        return False

    async def _parse_flights(self, route: Route, flight_date: date) -> List[dict]:
        """解析航班列表"""
        flights = []

        # 尝试多个选择器
        selectors = [
            '.flight-item',
            '.flight-list-item',
            '.flight-card',
            '[class*="flight"]'
        ]

        items = []
        for selector in selectors:
            items = await self.page.query_selector_all(selector)
            if items:
                break

        for item in items:
            try:
                flight = await self._parse_single_flight(item, route, flight_date)
                if flight:
                    flights.append(flight)
            except Exception as e:
                continue

        return flights

    async def _parse_single_flight(
        self,
        item,
        route: Route,
        flight_date: date
    ) -> Optional[dict]:
        """解析单个航班"""
        try:
            # 航班号
            flight_no = await self._get_text(item, ['.flight-no', '.flight-number'])

            # 航空公司
            airline = await self._get_text(item, ['.airline', '.company-name'])

            # 价格
            price_text = await self._get_text(item, ['.price', '.amount'])
            price_match = re.search(r'\d+', price_text)
            if not price_match:
                return None
            price = int(price_match.group())

            return {
                'flight_no': flight_no.strip() if flight_no else 'Unknown',
                'airline': airline.strip() if airline else 'Unknown',
                'price': price,
                'date': flight_date.isoformat(),
                'route_from': route.from_city,
                'route_to': route.to_city
            }

        except Exception:
            return None

    async def _get_text(self, item, selectors: list) -> str:
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
```

---

## Task 5: 通知模块

**Files:**
- Create: `src/notifier.py`

```python
"""
通知模块 - 支持邮件、Webhook、Bark
"""

import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List
import aiohttp
from src.config import NotificationsConfig, EmailConfig, WebhookConfig, BarkConfig
from src.exceptions import NotifierError


class Notifier:
    """通知管理器"""

    def __init__(self, config: NotificationsConfig):
        self.config = config
        self._history = set()  # 避免重复通知

    async def send_low_price_alert(self, flights: List[dict]) -> None:
        """
        发送低价提醒

        Args:
            flights: 低价航班列表，每个字典包含:
                - flight_no: 航班号
                - airline: 航空公司
                - price: 价格
                - date: 日期
                - route_from: 出发地
                - route_to: 目的地
        """
        for flight in flights:
            # 生成唯一标识避免重复通知
            alert_id = f"{flight['route_from']}-{flight['route_to']}-{flight['date']}-{flight['flight_no']}"

            if alert_id in self._history:
                continue

            self._history.add(alert_id)

            # 构建消息
            title = f"✈️ 低价机票: {flight['route_from']} → {flight['route_to']}"
            content = f"""
航班: {flight['flight_no']}
航空: {flight['airline']}
日期: {flight['date']}
价格: ¥{flight['price']}
            """.strip()

            # 发送通知
            tasks = []

            if self.config.email.enabled:
                tasks.append(self._send_email(title, content))

            if self.config.webhook.enabled:
                tasks.append(self._send_webhook(title, content))

            if self.config.bark.enabled:
                tasks.append(self._send_bark(title, content))

            if tasks:
                import asyncio
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_email(self, title: str, content: str) -> None:
        """发送邮件"""
        cfg = self.config.email

        try:
            msg = MIMEMultipart()
            msg['From'] = cfg.username
            msg['To'] = ', '.join(cfg.to)
            msg['Subject'] = title

            msg.attach(MIMEText(content, 'plain', 'utf-8'))

            with smtplib.SMTP_SSL(cfg.smtp_server, cfg.smtp_port) as server:
                server.login(cfg.username, cfg.password)
                server.send_message(msg)

        except Exception as e:
            raise NotifierError(f"邮件发送失败: {e}")

    async def _send_webhook(self, title: str, content: str) -> None:
        """发送Webhook"""
        cfg = self.config.webhook

        try:
            payload = {
                "msgtype": "text",
                "text": {"content": f"{title}\n\n{content}"}
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(cfg.url, json=payload) as resp:
                    if resp.status != 200:
                        raise NotifierError(f"Webhook返回错误: {resp.status}")

        except Exception as e:
            raise NotifierError(f"Webhook发送失败: {e}")

    async def _send_bark(self, title: str, content: str) -> None:
        """发送Bark推送"""
        cfg = self.config.bark

        try:
            import urllib.parse
            encoded_title = urllib.parse.quote(title)
            encoded_content = urllib.parse.quote(content)

            url = f"{cfg.server}/{cfg.device_key}/{encoded_title}/{encoded_content}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise NotifierError(f"Bark返回错误: {resp.status}")

        except Exception as e:
            raise NotifierError(f"Bark发送失败: {e}")
```

---

## Task 6: 主程序

**Files:**
- Create: `main.py`

```python
#!/usr/bin/env python3
"""
FlightFind - 携程机票价格监控工具

用法:
    python main.py [config_path]

参数:
    config_path: 配置文件路径，默认为 config.yaml
"""

import sys
import asyncio
import signal
from pathlib import Path
from src.config import load_config
from src.database import Database
from src.crawler import CtripCrawler
from src.notifier import Notifier
from src.utils import setup_logging
import logging

logger = logging.getLogger(__name__)


class FlightMonitor:
    """机票监控主类"""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = None
        self.db = None
        self.crawler = None
        self.notifier = None
        self.running = False

    async def init(self) -> None:
        """初始化"""
        # 加载配置
        self.config = load_config(self.config_path)

        # 初始化日志
        setup_logging(
            log_file=Path("logs/monitor.log"),
            level=logging.INFO
        )

        logger.info("=" * 50)
        logger.info("FlightFind 机票监控工具启动")
        logger.info("=" * 50)

        # 初始化数据库
        self.db = Database(Path("data/flights.db"))
        await self.db.init()
        logger.info("数据库初始化完成")

        # 初始化爬虫
        self.crawler = CtripCrawler(headless=self.config.monitor.headless)
        await self.crawler.init()
        logger.info("浏览器初始化完成")

        # 初始化通知器
        self.notifier = Notifier(self.config.notifications)
        logger.info("通知模块初始化完成")

        logger.info(f"配置航线数量: {len(self.config.routes)}")
        for route in self.config.routes:
            logger.info(f"  - {route.from_city} -> {route.to_city} (阈值: ¥{route.low_price_threshold})")

    async def run_check(self) -> None:
        """执行一次检查"""
        if not self.crawler:
            logger.error("爬虫未初始化")
            return

        for route in self.config.routes:
            for flight_date in route.dates.absolute_dates:
                try:
                    logger.info(f"检查: {route.from_city} -> {route.to_city} ({flight_date})")

                    flights = await self.crawler.search_flights(route)

                    if not flights:
                        logger.warning(f"未找到航班: {route.from_city} -> {route.to_city}")
                        continue

                    # 保存价格历史
                    for flight in flights:
                        await self.db.save_price_history(
                            route_from=flight['route_from'],
                            route_to=flight['route_to'],
                            flight_date=flight_date,
                            flight_no=flight['flight_no'],
                            airline=flight['airline'],
                            price=flight['price']
                        )

                    # 检查低价
                    low_prices = [f for f in flights if f['price'] <= route.low_price_threshold]

                    if low_prices:
                        logger.info(f"发现 {len(low_prices)} 个低价航班！")
                        await self.notifier.send_low_price_alert(low_prices)

                        # 保存提醒记录
                        for flight in low_prices:
                            await self.db.save_alert(
                                route_from=flight['route_from'],
                                route_to=flight['route_to'],
                                flight_date=flight_date,
                                flight_no=flight['flight_no'],
                                airline=flight['airline'],
                                price=flight['price'],
                                threshold=route.low_price_threshold,
                                channels=self._get_enabled_channels()
                            )
                    else:
                        min_price = min(f['price'] for f in flights)
                        logger.info(f"最低价格: ¥{min_price} (阈值: ¥{route.low_price_threshold})")

                except Exception as e:
                    logger.error(f"检查失败: {route.from_city} -> {route.to_city} - {e}")

    def _get_enabled_channels(self) -> List[str]:
        """获取启用的通知渠道"""
        channels = []
        if self.config.notifications.email.enabled:
            channels.append('email')
        if self.config.notifications.webhook.enabled:
            channels.append('webhook')
        if self.config.notifications.bark.enabled:
            channels.append('bark')
        return channels

    async def close(self) -> None:
        """清理资源"""
        logger.info("正在关闭...")

        if self.crawler:
            await self.crawler.close()

        logger.info("已关闭")


async def main():
    """主函数"""
    # 获取配置文件路径
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.yaml")

    if not config_path.exists():
        print(f"错误: 配置文件不存在: {config_path}")
        print(f"请复制 config.example.yaml 到 {config_path} 并修改")
        sys.exit(1)

    monitor = FlightMonitor(config_path)

    # 设置信号处理
    def signal_handler(sig, frame):
        print("\n收到终止信号，正在关闭...")
        asyncio.create_task(monitor.close())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 初始化
        await monitor.init()

        # 执行一次检查
        await monitor.run_check()

    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        logger.exception(f"运行时错误: {e}")
        sys.exit(1)
    finally:
        await monitor.close()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 总结

本实施计划包含以下主要任务：

1. **项目基础结构** - requirements.txt, config.example.yaml, 异常定义
2. **配置管理模块** - 完整的配置加载和验证系统
3. **数据库模块** - SQLite 数据库操作，包含价格历史、低价提醒、执行日志
4. **爬虫模块** - Playwright 浏览器自动化，支持反爬检测
5. **通知模块** - 邮件、Webhook、Bark 多渠道通知
6. **主程序** - 完整的命令行工具，支持配置文件参数

所有模块都遵循以下设计原则：
- 使用 async/await 异步编程
- 完善的错误处理和重试机制
- 详细的日志记录
- 模块化的接口设计
