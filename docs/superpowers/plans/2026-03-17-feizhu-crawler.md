# Feizhu Crawler Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Feizhu (飞猪) as an alternative data source to the existing Ctrip crawler, implementing an abstract base class architecture that allows users to switch between data sources via configuration.

**Architecture:** Create an abstract `FlightCrawler` base class that defines the crawler interface. Both `CtripCrawler` and `FeizhuCrawler` will inherit from it. A crawler factory in `FlightMonitor` will instantiate the appropriate crawler based on `default_source` configuration.

**Tech Stack:** Python 3.12+, Playwright, aiosqlite, PyYAML, pytest

---

## File Structure

```
src/
├── base_crawler.py          [NEW] Abstract base class
├── crawler.py                [MODIFY] Refactor to inherit from base
├── feizhu_crawler.py         [NEW] Feizhu implementation
├── config.py                 [MODIFY] Add default_source and validation
├── database.py                [MODIFY] Add source migration and parameters
├── notifier.py                [MODIFY] Update message templates and deduplication
└── __init__.py               [NO CHANGE]

config.example.yaml               [MODIFY] Add default_source example
docs/superpowers/specs/         [NO CHANGE] Design spec exists
docs/superpowers/plans/          [NO CHANGE] This file
```

---

## Chunk 1: Base Class and Ctrip Refactoring

### Task 1: Abstract Base Class

**Files:**
- Create: `src/base_crawler.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_base_crawler.py
import pytest
from src.base_crawler import FlightCrawler

def test_cannot_instantiate_base_class():
    """Cannot instantiate abstract class"""
    with pytest.raises(TypeError):
        crawler = FlightCrawler()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_base_crawler.py::test_cannot_instantiate_base_class -v`
Expected: FAIL with "Can't instantiate abstract class"

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_base_crawler.py::test_cannot_instantiate_base_class -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/base_crawler.py tests/test_base_crawler.py
git commit -m "feat: add FlightCrawler abstract base class"
```

---

### Task 2: Refactor CtripCrawler

**Files:**
- Modify: `src/crawler.py`

- [ ] **Step 1: Update imports and class declaration**

Add import and change class to inherit from base:

```python
from src.base_crawler import FlightCrawler

class CtripCrawler(FlightCrawler):
    source = "ctrip"
    # ... rest of implementation
```

- [ ] **Step 2: Remove date field from return dict**

In `_parse_single_flight()` method, remove this line:

```python
# REMOVE: 'date': flight_date.isoformat(),
```

- [ ] **Step 3: Add source to return dict**

Add source field to the return dictionary:

```python
return {
    'flight_no': flight_no.strip() if flight_no else 'Unknown',
    'airline': airline.strip() if airline else 'Unknown',
    'price': price,
    'route_from': route.from_city,
    'route_to': route.to_city,
    'source': self.source  # NEW: add source field
}
```

- [ ] **Step 4: Update __init__ parameters**

Keep existing Ctrip-specific parameters:

```python
def __init__(self, headless: bool = True, debug_save_html: bool = False,
             debug_html_path: Optional[Path] = None,
             page_load_timeout: int = 45000):
    super().__init__(headless)
    self.debug_save_html = debug_save_html
    self.debug_html_path = debug_html_path or Path("./logs")
    self.page_load_timeout = page_load_timeout
    # ... rest of __init__
```

- [ ] **Step 5: Test Ctrip crawler still works**

Run: `python main.py config.yaml`
Expected: Ctrip crawler runs successfully with source field

- [ ] **Step 6: Commit**

```bash
git add src/crawler.py
git commit -m "refactor: CtripCrawler inherits from FlightCrawler, add source field"
```

---

## Chunk 2: Configuration

### Task 3: Config Dataclass Updates

**Files:**
- Modify: `src/config.py`

- [ ] **Step 1: Add default_source to MonitorConfig**

```python
@dataclass
class MonitorConfig:
    default_source: str = "feizhu"  # NEW: default to Feizhu
    headless: bool = True
    check_interval: int = 60
```

- [ ] **Step 2: Add validation function**

```python
def _validate_config(config: AppConfig) -> None:
    # ... existing validations ...

    # NEW: Validate default_source
    valid_sources = {'ctrip', 'feizhu'}
    if config.monitor.default_source not in valid_sources:
        raise ConfigError(
            f"default_source must be one of {valid_sources}, "
            f"got: {config.monitor.default_source}"
        )
```

- [ ] **Step 3: Call validation in load_config**

```python
def load_config(config_path: Path) -> AppConfig:
    # ... load config ...
    _validate_config(config)
    return config
```

- [ ] **Step 4: Test config validation**

Run: `python -c "from src.config import load_config; load_config(Path('config.yaml'))"`
Expected: Success if default_source is valid

- [ ] **Step 5: Commit**

```bash
git add src/config.py
git commit -m "feat: add default_source to config with validation"
```

---

### Task 4: Config Example File

**Files:**
- Modify: `config.example.yaml`

- [ ] **Step 1: Add default_source option**

```yaml
monitor:
  default_source: "feizhu"  # 数据源: "ctrip" 或 "feizhu"
  headless: true
```

- [ ] **Step 2: Commit**

```bash
git add config.example.yaml
git commit -m "docs: add default_source to config example"
```

---

## Chunk 3: Database Migration

### Task 5: Database Migration Method

**Files:**
- Modify: `src/database.py`

- [ ] **Step 1: Add migration method**

```python
async def migrate_add_source_column(self) -> None:
    """Migration to add source column to all tables"""
    async with self._get_connection() as db:
        for table in ['price_history', 'low_price_alerts', 'execution_logs']:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN source TEXT DEFAULT 'ctrip'")
                logger.info(f"Added source column to {table}")
            except aiosqlite.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_price_source ON price_history(source)",
            "CREATE INDEX IF NOT EXISTS idx_alert_source ON low_price_alerts(source)",
            "CREATE INDEX IF NOT EXISTS idx_log_source ON execution_logs(source)"
        ]
        for index_sql in indexes:
            try:
                await db.execute(index_sql)
            except aiosqlite.OperationalError:
                pass
        await db.commit()
```

- [ ] **Step 2: Call migration in init()**

```python
async def init(self, db_path: Path) -> None:
    # ... existing initialization ...
    await self.migrate_add_source_column()
```

- [ ] **Step 3: Test migration on existing database**

Run: `python -c "from src.database import Database; import asyncio; asyncio.run(Database(Path('data/flights.db').migrate_add_source_column())"`
Expected: Logs "Added source column to [table]" for each table

- [ ] **Step 4: Commit**

```bash
git add src/database.py
git commit -m "feat: add database migration for source column"
```

---

### Task 6: Database API Updates

**Files:**
- Modify: `src/database.py`

- [ ] **Step 1: Update save_price_history signature**

```python
async def save_price_history(
    self,
    route_from: str,
    route_to: str,
    flight_date: str,
    flight_no: str,
    airline: str,
    price: int,
    source: str = "ctrip"  # NEW: add source parameter with default
) -> None:
    sql = """
        INSERT INTO price_history
        (route_from, route_to, flight_date, flight_no, airline, price, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    await db.execute(sql, (route_from, route_to, flight_date, flight_no, airline, price, source))
    await db.commit()
```

- [ ] **Step 2: Update save_alert signature**

```python
async def save_alert(
    self,
    route_from: str,
    route_to: str,
    flight_date: str,
    flight_no: str,
    airline: str,
    price: int,
    threshold: int,
    source: str = "ctrip",  # NEW: add source parameter
    channels: str = ""
) -> None:
    sql = """
        INSERT INTO low_price_alerts
        (route_from, route_to, flight_date, flight_no, airline, price, threshold, channels, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    await db.execute(sql, (route_from, route_to, flight_date, flight_no,
                      airline, price, threshold, channels, source))
    await db.commit()
```

- [ ] **Step 3: Update log_execution signature**

```python
async def log_execution(
    self,
    job_id: str,
    route_from: str,
    route_to: str,
    flight_date: str,
    status: str,
    message: str,
    execution_time_ms: int = 0,
    source: str = "ctrip"  # NEW: add source parameter
) -> None:
    sql = """
        INSERT INTO execution_logs
        (job_id, route_from, route_to, flight_date, status, message, execution_time_ms, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    await db.execute(sql, (job_id, route_from, route_to, flight_date,
                      status, message, execution_time_ms, source))
    await db.commit()
```

- [ ] **Step 4: Commit**

```bash
git add src/database.py
git commit -m "feat: add source parameter to database methods"
```

---

## Chunk 4: Notifier Updates

### Task 7: Update Notifier Signatures

**Files:**
- Modify: `src/notifier.py`

- [ ] **Step 1: Update send_low_price_alert signature**

```python
async def send_low_price_alert(
    self,
    flights: List[Dict[str, Any]],
    flight_date: date,  # NEW: add flight_date parameter
    threshold: int  # NEW: add threshold parameter
) -> None:
    for flight in flights:
        await self._send_single_alert(flight, flight_date, threshold)
```

- [ ] **Step 2: Update _send_single_alert signature**

```python
async def _send_single_alert(
    self,
    flight: Dict[str, Any],
    flight_date: date,  # NEW: add flight_date parameter
    threshold: int  # NEW: add threshold parameter
) -> None:
    # ... existing implementation
```

- [ ] **Step 3: Update deduplication key**

```python
alert_id = f"{flight['route_from']}-{flight['route_to']}-{flight_date.isoformat()}-{flight['flight_no']}-{flight['source']}"
```

- [ ] **Step 4: Commit**

```bash
git add src/notifier.py
git commit -m "refactor: update notifier signatures for flight_date and threshold"
```

---

### Task 8: Update Message Templates

**Files:**
- Modify: `src/notifier.py`

- [ ] **Step 1: Update email template**

```python
# In _send_email() method
source_label = f"【{flight.get('source', '未知')}】"
subject = f"{source_label}低价航班提醒"
body = f"""
{source_label}{flight.get('route_from', '')} → {flight.get('route_to', '')} ({flight_date})
航班: {flight.get('flight_no', '')} ({flight.get('airline', '')})
价格: ¥{flight.get('price', 0)}
阈值: ¥{threshold}
"""
```

- [ ] **Step 2: Update webhook message**

```python
# In _send_webhook() method
content = f"【{flight.get('source', '未知')}】低价航班提醒\n{flight.get('route_from', '')} → {flight.get('route_to', '')} ({flight_date})\n航班: {flight.get('flight_no', '')} ({flight.get('airline', '')})\n价格: ¥{flight.get('price', 0)} (低于阈值 ¥{threshold})"
```

- [ ] **Step 3: Update bark message**

```python
# In _send_bark() method
content = f"【{flight.get('source', '未知')}】{flight.get('route_from', '')}→{flight.get('route_to', '')} ¥{flight.get('price', 0)}\n{flight.get('flight_no', '')} {flight.get('airline', '')}"
```

- [ ] **Step 4: Commit**

```bash
git add src/notifier.py
git commit -m "feat: add source label to notification messages"
```

---

## Chunk 5: Crawler Factory

### Task 9: Update FlightMonitor

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add crawler factory logic**

```python
# In FlightMonitor.init() method
if self.config.monitor.default_source == "feizhu":
    from src.feizhu_crawler import FeizhuCrawler
    self.crawler = FeizhuCrawler(headless=self.config.monitor.headless)
else:
    self.crawler = CtripCrawler(headless=self.config.monitor.headless)

await self.crawler.init()
logger.info(f"使用数据源: {self.config.monitor.default_source}")
```

- [ ] **Step 2: Update database calls to pass source**

```python
# In run_check() method - save_price_history call
await self.db.save_price_history(
    route_from=flight['route_from'],
    route_to=flight['route_to'],
    flight_date=flight_date,
    flight_no=flight['flight_no'],
    airline=flight['airline'],
    price=flight['price'],
    source=flight['source']  # NEW: pass source
)
```

- [ ] **Step 3: Update save_alert call**

```python
# In run_check() method - save_alert call
await self.db.save_alert(
    route_from=flight['route_from'],
    route_to=flight['route_to'],
    flight_date=flight_date,
    flight_no=flight['flight_no'],
    airline=flight['airline'],
    price=flight['price'],
    threshold=route.low_price_threshold,
    source=flight['source'],  # NEW: pass source
    channels=channels
)
```

- [ ] **Step 4: Update log_execution call**

```python
# In run_check() method - log_execution calls
source = self.crawler.source if hasattr(self.crawler, 'source') else self.config.monitor.default_source

await self.db.log_execution(
    job_id=job_id,
    route_from=route.from_city,
    route_to=route.to_city,
    flight_date=flight_date.isoformat(),
    status=status,
    message=message,
    execution_time_ms=execution_time,
    source=source  # NEW: pass source
)
```

- [ ] **Step 5: Update notifier call**

```python
# In run_check() method - send_low_price_alert call
await self.notifier.send_low_price_alert(low_price_flights, flight_date, route.low_price_threshold)
```

- [ ] **Step 6: Commit**

```bash
git add main.py
git commit -m "feat: add crawler factory and pass source to database/notifier"
```

---

## Chunk 6: Feizhu Crawler Implementation

### Task 10: Create FeizhuCrawler Skeleton

**Files:**
- Create: `src/feizhu_crawler.py`

- [ ] **Step 1: Create basic structure**

```python
"""
飞猪爬虫模块
"""

import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import date
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
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
        # TODO: Investigate actual Feizhu URL format
        from_code = get_feizhu_city_code(from_city)
        to_code = get_feizhu_city_code(to_city)
        # Placeholder URL - to be replaced after investigation
        return f"https://www.fliggy.com/trip/oneway/{from_code}-{to_code}?depdate={date_str}"

    async def _parse_flights(self, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        """解析航班列表"""
        # TODO: Implement Feizhu-specific CSS selectors
        return []

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
```

- [ ] **Step 2: Commit skeleton**

```bash
git add src/feizhu_crawler.py
git commit -m "feat: add FeizhuCrawler skeleton"
```

---

### Task 11: Investigate Feizhu URL and Selectors

**Action Item (not code):** Manual investigation required

- [ ] **Step 1: Visit fliggy.com**

Open `https://www.fliggy.com` in a browser

- [ ] **Step 2: Perform manual search**

Search for a domestic flight route (e.g., 深圳 → 上海)

- [ ] **Step 3: Capture URL format**

Note the actual search URL pattern and parameters

- [ ] **Step 4: Identify CSS selectors**

Use browser DevTools to identify flight element classes

- [ ] **Step 5: Document findings**

Update `src/feizhu_crawler.py` with actual URL and selectors

---

### Task 12: Complete Feizhu Implementation

**Files:**
- Modify: `src/feizhu_crawler.py`

- [ ] **Step 1: Update _build_search_url with actual format**

Replace placeholder with discovered URL format

- [ ] **Step 2: Update _parse_flights with actual selectors**

Implement Feizhu-specific parsing logic

- [ ] **Step 3: Test Feizhu crawler**

Run: `python -c "from src.feizhu_crawler import FeizhuCrawler; import asyncio; asyncio.run(asyncio.run(asyncio.run(asyncio.run(asyncio.run(asyncio.run(asyncio.run()))))"` (create simple test)
Expected: No syntax errors

- [ ] **Step 4: Commit**

```bash
git add src/feizhu_crawler.py
git commit -m "feat: complete FeizhuCrawler implementation"
```

---

## Chunk 7: Testing

### Task 13: Integration Test

- [ ] **Step 1: Test with Feizhu source**

Update `config.yaml` to use Feizhu:
```yaml
monitor:
  default_source: "feizhu"
```

Run: `python main.py config.yaml`
Expected: Monitor uses Feizhu crawler

- [ ] **Step 2: Test with Ctrip source**

Update `config.yaml` to use Ctrip:
```yaml
monitor:
  default_source: "ctrip"
```

Run: `python main.py config.yaml`
Expected: Monitor uses Ctrip crawler

- [ ] **Step 3: Commit config changes**

```bash
git add config.yaml
git commit -m "test: switch data source between ctrip and feizhu"
```

---

## Summary Checklist

### Implementation Tasks (Complete all)

- [ ] Task 1: Abstract base class
- [ ] Task 2: CtripCrawler refactor
- [ ] Task 3: Config dataclass
- [ ] Task 4: Config example
- [ ] Task 5: Database migration method
- [ ] Task 6: Database API updates
- [ ] Task 7: Notifier signatures
- [ ] Task 8: Notifier templates
- [ ] Task 9: Crawler factory in main.py
- [ ] Task 10: FeizhuCrawler skeleton
- [ ] Task 11: Feizhu investigation
- [ ] Task 12: Feizhu implementation
- [ ] Task 13: Integration testing

### Manual Verification

After completing all tasks:

1. **Run monitor with Feizhu source** - Verify it works end-to-end
2. **Run monitor with Ctrip source** - Verify Ctrip still works
3. **Check database** - Verify source column is populated correctly
4. **Test notifications** - Verify source label appears in alerts
5. **Verify deduplication** - Same flight from different sources should trigger separate alerts
