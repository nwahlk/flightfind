# FlightFind 机票价格监控工具 - 设计文档

**版本**: 1.0
**日期**: 2025-03-14
**作者**: Claude Code

---

## 1. 项目概述

### 1.1 目标
开发一个本地运行的机票价格监控工具，自动检查携程网站指定航线的机票价格，发现低于设定阈值的低价票时，通过多种渠道（邮件、微信、推送）通知用户。

### 1.2 核心功能
- 多航线监控，每条航线独立配置日期和价格阈值
- 使用 Playwright 模拟浏览器访问携程，获取实时价格
- 支持绝对日期配置（如 2025-04-01）
- 多渠道通知：邮件、企业微信/钉钉 Webhook、Bark 推送
- 价格历史记录，方便分析价格趋势
- 本地 SQLite 存储，无需外部数据库

### 1.3 非功能需求
- **部署简单**：单机运行，一个配置文件即可启动
- **资源友好**：无界面浏览器运行，占用资源少
- **稳定可靠**：网络异常自动重试，浏览器崩溃自动恢复
- **可扩展**：代码结构清晰，方便添加新通知渠道或数据源

---

## 2. 系统架构

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      用户层 (本地运行)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  config.yaml│  │  flights.db │  │  monitor.log        │  │
│  │  (配置文件)  │  │ (SQLite DB) │  │  (日志文件)          │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     核心监控引擎                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐  │
│  │   调度器        │  │   爬虫引擎       │  │   价格解析器  │  │
│  │ (APScheduler)   │  │ (Playwright)    │  │(BeautifulSoup)│ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     通知模块                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  邮件(SMTP)  │  │  Webhook    │  │  Bark推送           │  │
│  │ (smtplib)   │  │ (企业微信等) │  │ (HTTP API)          │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块职责

| 模块 | 核心职责 | 关键技术 |
|------|----------|----------|
| ConfigManager | 加载、验证、热更新配置文件 | PyYAML, Pydantic |
| Database | 价格历史存储、查询、统计 | SQLite, aiosqlite |
| Crawler | 模拟浏览器访问携程，获取页面 | Playwright |
| Parser | 解析HTML，提取航班和价格信息 | BeautifulSoup, lxml |
| Scheduler | 定时触发检查任务，管理并发 | APScheduler |
| Notifier | 多渠道发送通知 | smtplib, aiohttp |
| Logger | 分级日志记录 | logging |

---

## 3. 数据模型

### 3.1 配置文件结构 (config.yaml)

```yaml
# 监控配置
monitor:
  check_interval: 60  # 检查间隔，单位：分钟
  headless: true      # true=无界面运行，false=显示浏览器窗口（调试用）

# 航线列表（每条航线独立配置日期）
routes:
  - from: "深圳"
    to: "上海"
    low_price_threshold: 800
    dates:  # 该航线特有日期配置
      mode: "absolute"  # absolute=固定日期
      absolute_dates: ["2025-04-02", "2025-04-03", "2025-04-04"]

  - from: "上海"
    to: "深圳"
    low_price_threshold: 600
    dates:
      mode: "absolute"
      absolute_dates: ["2025-04-04", "2025-04-05", "2025-04-06"]

# 全局默认日期配置（如某航线未配置dates，则使用此处）
default_dates:
  mode: "absolute"
  absolute_dates: []

# 通知配置（任意配置了的发送）
notifications:
  # 邮件通知
  email:
    enabled: true
    smtp_server: "smtp.qq.com"
    smtp_port: 465
    username: "275381922@qq.com"
    password: "Nwahlk353535"
    to: ["275381922@qq.com"]

  # 企业微信/钉钉/飞书 Webhook
  webhook:
    enabled: false
    url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx"

  # Bark推送（iOS）
  bark:
    enabled: false
    device_key: "your_device_key"
    server: "https://api.day.app"
```

### 3.2 数据库表结构 (SQLite)

```sql
-- 价格历史记录表
CREATE TABLE price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_from TEXT NOT NULL,        -- 出发地
    route_to TEXT NOT NULL,          -- 目的地
    flight_date DATE NOT NULL,       -- 航班日期
    flight_no TEXT,                  -- 航班号
    airline TEXT,                    -- 航空公司
    price INTEGER NOT NULL,          -- 价格（元）
    check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(route_from, route_to, flight_date, flight_no, check_time)
);

-- 低价提醒记录表
CREATE TABLE low_price_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_from TEXT NOT NULL,
    route_to TEXT NOT NULL,
    flight_date DATE NOT NULL,
    flight_no TEXT,
    airline TEXT,
    price INTEGER NOT NULL,
    threshold INTEGER NOT NULL,        -- 触发的阈值
    alert_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notified BOOLEAN DEFAULT FALSE,    -- 是否已发送通知
    notification_channels TEXT         -- 使用的通知渠道，JSON格式
);

-- 监控任务执行日志
CREATE TABLE job_execution_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    route_from TEXT,
    route_to TEXT,
    flight_date TEXT,
    status TEXT NOT NULL,              -- success / failed
    message TEXT,                      -- 错误或成功信息
    execution_time_ms INTEGER,         -- 执行耗时（毫秒）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引加速查询
CREATE INDEX idx_price_route ON price_history(route_from, route_to);
CREATE INDEX idx_price_date ON price_history(flight_date);
CREATE INDEX idx_price_check ON price_history(check_time);
CREATE INDEX idx_alert_notified ON low_price_alerts(notified);
CREATE INDEX idx_job_status ON job_execution_logs(status, created_at);
```

### 3.3 Python 数据类定义

```python
from dataclasses import dataclass
from typing import List, Literal, Optional
from datetime import date, datetime

# ============ 配置相关 ============

@dataclass
class DateConfig:
    """日期配置"""
    mode: Literal["absolute", "relative"]
    absolute_dates: List[date]  # mode=absolute 时使用
    relative_days: List[int]    # mode=relative 时使用

@dataclass
class Route:
    """航线配置"""
    from_city: str
    to_city: str
    low_price_threshold: int
    dates: DateConfig  # 每个航线独立配置日期

@dataclass
class EmailConfig:
    enabled: bool
    smtp_server: str
    smtp_port: int
    username: str
    password: str
    to: List[str]

@dataclass
class WebhookConfig:
    enabled: bool
    url: str

@dataclass
class BarkConfig:
    enabled: bool
    device_key: str
    server: str

@dataclass
class MonitorConfig:
    check_interval: int  # 分钟
    headless: bool

@dataclass
class Config:
    """完整配置"""
    monitor: MonitorConfig
    routes: List[Route]
    default_dates: DateConfig
    notifications: dict  # email, webhook, bark

# ============ 运行时数据 ============

@dataclass
class FlightPrice:
    """航班价格信息"""
    route: Route
    date: date                    # 航班日期
    flight_no: str                # 航班号
    airline: str                  # 航空公司
    price: int                    # 价格（元）
    check_time: datetime          # 检查时间

    @property
    def is_low_price(self) -> bool:
        """是否为低价"""
        return self.price <= self.route.low_price_threshold

@dataclass
class CheckResult:
    """单次检查结果"""
    route: Route
    date: date
    flights: List[FlightPrice]
    low_price_flights: List[FlightPrice]
    execution_time_ms: int
    success: bool
    error_message: Optional[str] = None
```

---

## 4. 模块接口定义

### 4.1 Crawler 接口

```python
class ICrawler(ABC):
    """爬虫接口"""

    @abstractmethod
    async def init(self) -> None:
        """初始化浏览器资源"""
        pass

    @abstractmethod
    async def search_flights(self, route: Route) -> List[FlightPrice]:
        """
        搜索指定航线的航班价格

        Args:
            route: 航线配置

        Returns:
            航班价格列表

        Raises:
            CrawlerError: 爬取失败（网络错误、页面解析失败等）
            AntiBotDetectedError: 被反爬检测
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭浏览器资源"""
        pass
```

### 4.2 Notifier 接口

```python
class INotifier(ABC):
    """通知器接口"""

    @abstractmethod
    async def send_low_price_alert(self, flights: List[FlightPrice]) -> None:
        """
        发送低价提醒

        Args:
            flights: 低价航班列表

        Raises:
            NotificationError: 所有通知渠道均发送失败
        """
        pass
```

### 4.3 Database 接口

```python
class IDatabase(ABC):
    """数据库接口"""

    @abstractmethod
    async def save_price_history(self, flights: List[FlightPrice]) -> None:
        """保存价格历史记录"""
        pass

    @abstractmethod
    async def record_alert(self, flight: FlightPrice, channels: List[str]) -> None:
        """记录低价提醒"""
        pass

    @abstractmethod
    async def get_price_history(self, route: Route, days: int = 30) -> List[PriceHistory]:
        """获取指定航线的历史价格"""
        pass
```

### 4.4 Scheduler 接口

```python
class IScheduler(ABC):
    """调度器接口"""

    @abstractmethod
    def add_route_job(self, route: Route) -> None:
        """为航线添加定时任务"""
        pass

    @abstractmethod
    def start(self) -> None:
        """启动调度器"""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """关闭调度器"""
        pass
```

## 5. 错误处理与重试策略

### 5.1 错误分类

| 错误类型 | 说明 | 处理策略 |
|----------|------|----------|
| `NetworkError` | 网络连接失败、DNS错误 | 指数退避重试(1s, 2s, 4s, 8s, 16s)，最多5次 |
| `TimeoutError` | 页面加载超时 | 重试3次，间隔5秒；仍失败则标记该次检查失败 |
| `ParseError` | 页面解析失败 | 记录错误日志，发送告警通知（可能是携程改版） |
| `AntiBotError` | 被反爬检测（验证码、滑块等） | 暂停30分钟，增加随机延迟后重试 |
| `BrowserCrashError` | 浏览器崩溃 | 自动重启浏览器实例，重新初始化Playwright |
| `DatabaseError` | 数据库写入失败 | 缓存到内存队列，定时重试；启动时检查并恢复 |

### 5.2 重试装饰器实现

```python
from functools import wraps
from typing import Type, Tuple
import asyncio
import random

class RetryConfig:
    """重试配置"""
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions

def async_retry(config: RetryConfig = None):
    """异步函数重试装饰器"""
    if config is None:
        config = RetryConfig()

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, config.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)

                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt == config.max_attempts:
                        logger.error(f"{func.__name__} 重试{config.max_attempts}次后仍然失败: {e}")
                        raise last_exception

                    # 计算延迟时间（指数退避 + 抖动）
                    delay = min(
                        config.base_delay * (config.exponential_base ** (attempt - 1)),
                        config.max_delay
                    )

                    if config.jitter:
                        delay = delay * (0.5 + random.random() * 0.5)  # 50%-150% 抖动

                    logger.warning(f"{func.__name__} 第{attempt}次尝试失败: {e}，{delay:.1f}秒后重试...")
                    await asyncio.sleep(delay)

            raise last_exception

        return wrapper
    return decorator
```

### 5.3 爬虫模块错误处理示例

```python
class CtripCrawler(ICrawler):
    """携程爬虫实现"""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._init_retry_config = RetryConfig(
            max_attempts=3,
            base_delay=2.0,
            retryable_exceptions=(BrowserCrashError, PlaywrightError)
        )

    @async_retry(RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        retryable_exceptions=(TimeoutError, NetworkError)
    ))
    async def init(self) -> None:
        """初始化浏览器（带重试）"""
        try:
            self.playwright = await async_playwright().start()

            # 启动参数优化
            browser_args = [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--no-first-run',
                '--disable-blink-features=AutomationControlled'
            ]

            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=browser_args
            )

            # 上下文配置（反检测）
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='zh-CN',
                timezone_id='Asia/Shanghai'
            )

            # 注入反检测脚本
            await self.context.add_init_script(path='stealth.min.js')

            logger.info("浏览器初始化成功")

        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            raise BrowserCrashError(f"浏览器初始化失败: {e}")

    @async_retry(RetryConfig(
        max_attempts=3,
        base_delay=5.0,
        retryable_exceptions=(NetworkError, TimeoutError, ParseError)
    ))
    async def search_flights(self, route: Route) -> List[FlightPrice]:
        """
        搜索航班（带重试）

        重试策略:
        - 网络超时: 3次重试，基础延迟5秒
        - 解析失败: 同上（可能是携程页面结构临时变化）
        - 被反爬检测: 不重试，直接抛出AntiBotError
        """
        if not self.page:
            self.page = await self.context.new_page()

        try:
            # 构建URL
            date_str = route.dates.absolute_dates[0].strftime('%Y-%m-%d')
            url = self._build_search_url(route.from_city, route.to_city, date_str)

            # 访问页面（带超时）
            response = await self.page.goto(url, wait_until='networkidle', timeout=30000)

            if not response or response.status != 200:
                raise NetworkError(f"页面加载失败: HTTP {response.status if response else 'None'}")

            # 检查是否被反爬
            if await self._detect_anti_bot():
                raise AntiBotError("检测到反爬验证（验证码/滑块等）")

            # 等待航班列表加载
            await self.page.wait_for_selector('.flight-list-item, .flight-item', timeout=15000)

            # 解析价格
            flights = await self._parse_flight_data(route, date_str)

            if not flights:
                logger.warning(f"未找到任何航班: {route.from_city}->{route.to_city} {date_str}")

            return flights

        except AntiBotError:
            # 被反爬检测，不重试，抛出让上层处理
            raise
        except Exception as e:
            logger.error(f"搜索航班失败: {e}")
            raise ParseError(f"搜索航班失败: {e}")

    async def _detect_anti_bot(self) -> bool:
        """检测是否触发反爬"""
        # 检查常见反爬标识
        anti_bot_selectors = [
            '.captcha',           # 验证码
            '#captcha',
            '.slider',            # 滑块
            '.verify-code',
            '[class*="anti"]',
            '[id*="captcha"]'
        ]

        for selector in anti_bot_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element and await element.is_visible():
                    return True
            except:
                continue

        # 检查页面内容是否包含"验证"等关键词
        page_text = await self.page.inner_text('body')
        anti_keywords = ['验证码', '请验证', '安全验证', '滑动验证', '请点击']
        for keyword in anti_keywords:
            if keyword in page_text:
                return True

        return False

    def _build_search_url(self, from_city: str, to_city: str, date: str) -> str:
        """构建携程搜索URL"""
        # 城市名转携程编码（需要实现映射）
        from_code = self._city_to_code(from_city)
        to_code = self._city_to_code(to_city)
        return f"https://flights.ctrip.com/online/channel/domestic?from={from_code}&to={to_code}&depart={date}"

    async def _parse_flight_data(self, route: Route, date: str) -> List[FlightPrice]:
        """解析航班数据"""
        flights = []

        # 尝试多种选择器（携程可能改版）
        selectors = [
            '.flight-item',
            '.flight-list-item',
            '[class*="flight"]',
            '.flight-card'
        ]

        items = []
        for selector in selectors:
            items = await self.page.query_selector_all(selector)
            if items:
                break

        if not items:
            logger.warning("未找到航班列表元素，可能页面结构已变更")
            return flights

        for item in items:
            try:
                flight = await self._parse_single_flight(item, route, date)
                if flight:
                    flights.append(flight)
            except Exception as e:
                logger.warning(f"解析单个航班失败: {e}")
                continue

        return flights

    async def _parse_single_flight(self, item: ElementHandle, route: Route, date: str) -> Optional[FlightPrice]:
        """解析单个航班信息"""
        try:
            # 航班号
            flight_no_selectors = ['.flight-no', '[class*="flight-no"]', '.flight-number']
            flight_no = await self._try_selectors(item, flight_no_selectors)

            # 航空公司
            airline_selectors = ['.airline', '[class*="airline"]', '.company-name']
            airline = await self._try_selectors(item, airline_selectors)

            # 价格
            price_selectors = ['.price', '[class*="price"]', '.amount', '.total-price']
            price_text = await self._try_selectors(item, price_selectors)
            price = int(re.search(r'\d+', price_text).group())

            return FlightPrice(
                route=route,
                date=date,
                flight_no=flight_no.strip() if flight_no else "Unknown",
                airline=airline.strip() if airline else "Unknown",
                price=price,
                check_time=datetime.now()
            )
        except Exception as e:
            logger.debug(f"解析航班字段失败: {e}")
            return None

    async def _try_selectors(self, item: ElementHandle, selectors: List[str]) -> str:
        """尝试多个选择器获取文本"""
        for selector in selectors:
            try:
                element = await item.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    if text:
                        return text
            except:
                continue
        return ""

    async def close(self) -> None:
        """关闭浏览器资源"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("浏览器资源已释放")
        except Exception as e:
            logger.error(f"关闭浏览器时出错: {e}")
```

## 5. 部署与使用说明

### 5.1 环境要求

- **Python**: 3.9+
- **操作系统**: Windows 10/11, macOS, Linux
- **内存**: 至少 2GB 可用内存
- **磁盘**: 至少 500MB 可用空间

### 5.2 安装步骤

```bash
# 1. 克隆或解压项目到本地
cd flightfind

# 2. 创建虚拟环境（推荐）
python -m venv venv

# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. 安装 Python 依赖
pip install -r requirements.txt

# 4. 安装 Playwright 浏览器
playwright install chromium
```

### 5.3 配置说明

1. 复制配置模板：
```bash
cp config.example.yaml config.yaml
```

2. 编辑 `config.yaml`，配置你的航线和通知方式。

3. 配置邮件通知（以 QQ 邮箱为例）：
   - SMTP服务器: `smtp.qq.com`
   - 端口: `465` (SSL)
   - 密码: 使用 QQ 邮箱的授权码，不是登录密码

### 5.4 运行程序

```bash
# 方式1: 直接运行
python main.py

# 方式2: 后台运行（Linux/macOS）
nohup python main.py > output.log 2>&1 &

# 方式3: 使用 pm2（需要安装 pm2）
pm2 start main.py --name flightfind
```

### 5.5 常见问题

**Q: 浏览器启动失败**
A: 确保已运行 `playwright install chromium`

**Q: 被携程检测到是爬虫**
A: 增加检查间隔时间（建议 30 分钟以上），避免频繁访问

**Q: 邮件发送失败**
A: 检查 SMTP 配置，确认使用的是授权码而非登录密码

---

## 6. 附录

### 6.1 项目结构

```
flightfind/
├── config.yaml              # 用户配置文件
├── config.example.yaml    # 配置模板
├── main.py                 # 主程序入口
├── requirements.txt        # Python 依赖
├── README.md              # 项目说明
├── docs/
│   └── specs/
│       └── 2025-03-14-flightfind-design.md  # 设计文档
├── src/
│   ├── __init__.py
│   ├── config.py          # 配置加载
│   ├── database.py        # 数据库操作
│   ├── crawler.py         # 爬虫逻辑
│   ├── parser.py          # 价格解析
│   ├── notifier.py        # 通知发送
│   ├── scheduler.py       # 调度管理
│   └── exceptions.py      # 异常定义
├── data/
│   └── flights.db         # SQLite 数据库（自动创建）
└── logs/
    └── monitor.log        # 运行日志（自动创建）
```

### 6.2 技术栈

- **浏览器自动化**: Playwright
- **调度**: APScheduler
- **数据库**: SQLite + aiosqlite
- **配置**: PyYAML + Pydantic
- **HTTP 请求**: aiohttp
- **邮件发送**: smtplib

---

**文档版本**: 1.0
**最后更新**: 2025-03-14