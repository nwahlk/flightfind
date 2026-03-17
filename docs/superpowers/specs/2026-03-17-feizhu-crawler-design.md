# Feizhu Crawler Integration Design

## Overview

Add Feizhu (飞猪) as an alternative data source to the existing Ctrip crawler. The system will support multiple data sources through an abstract base class architecture, allowing users to switch between Ctrip and Feizhu via configuration.

## Breaking Changes

This is a **breaking change** for existing users:

1. **Default source changes to "feizhu"** - Existing `config.yaml` files without `default_source` will now use Feizhu instead of Ctrip
2. **Flight dict format changes** - The `date` field will be removed from flight dictionaries returned by crawlers
3. **Database migration required** - Existing databases will be migrated to add `source` column

**Migration Path:**
- Existing databases will have `source` set to 'ctrip' for all historical data
- Users who want to continue using Ctrip should explicitly set `default_source: "ctrip"` in their config
- No automatic config migration needed - users who don't specify `default_source` will get the new default (feizhu)

**User Action Required:**
- Users who wish to continue using Ctrip must add `default_source: "ctrip"` to their `config.yaml` before running the updated code
- Otherwise, the system will default to Feizhu

## Architecture

### Abstract Base Class

Create `FlightCrawler` abstract base class in `src/base_crawler.py`:

```python
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

**Note:** Implementation-specific parameters (like `debug_save_html`, `page_load_timeout`) should be added directly to concrete classes (`CtripCrawler`, `FeizhuCrawler`) rather than the base class. Each crawler must define the `source` class attribute.

### Data Format

All crawlers must return flights in this standardized format:

```python
{
    'flight_no': str,      # 航班号，如 "MU5358"
    'airline': str,        # 航空公司，如 "深圳航空"
    'price': int,          # 价格（整数）
    'route_from': str,     # 出发城市
    'route_to': str,       # 目的城市
    'source': str          # 数据源，"ctrip" 或 "feizhu"
}
```

**Decision:** The `date` field is NOT included in the returned dict. This is a breaking change from the current `CtripCrawler` implementation which includes it.

**Refactoring Required:**
1. Remove `'date': flight_date.isoformat()` from `CtripCrawler._parse_single_flight()` return value
2. Update `main.py` to pass `date` from `route.dates` directly to database methods (already done in current code)
3. Update `Notifier._send_single_alert()` to accept `flight_date` as a separate parameter for deduplication

### Implementations

1. **CtripCrawler** (refactored)
   - Move existing implementation to inherit from `FlightCrawler`
   - Add `'source': 'ctrip'` to returned flight data
   - File: `src/crawler.py`

2. **FeizhuCrawler** (new)
   - Implement `FlightCrawler` interface
   - Feizhu-specific URL building and parsing
   - File: `src/feizhu_crawler.py`

## Configuration

### Config File

Update `config.yaml`:

```yaml
monitor:
  default_source: "feizhu"  # "ctrip" or "feizhu"
  headless: true
```

### Config Dataclass

Update `src/config.py` - `MonitorConfig` class:

```python
@dataclass
class MonitorConfig:
    default_source: str = "feizhu"  # Changed default from "ctrip"
    headless: bool = True
```

Add validation in `load_config()` or a separate `_validate_config()` function:

```python
def _validate_config(config: AppConfig) -> None:
    valid_sources = {'ctrip', 'feizhu'}
    if config.monitor.default_source not in valid_sources:
        raise ConfigError(f"default_source must be one of {valid_sources}, got: {config.monitor.default_source}")
```

### Config Example Update

Update `config.example.yaml` to show the new option:

```yaml
monitor:
  default_source: "feizhu"  # 数据源: "ctrip" 或 "feizhu"
  headless: true
```

## Crawler Factory

In `FlightMonitor.init()`, create crawler based on config:

```python
if self.config.monitor.default_source == "feizhu":
    self.crawler = FeizhuCrawler(headless=self.config.monitor.headless)
else:
    self.crawler = CtripCrawler(headless=self.config.monitor.headless)

await self.crawler.init()
logger.info(f"使用数据源: {self.config.monitor.default_source}")
```

**Note:** Each crawler should have a `source` class attribute that returns its name ('ctrip' or 'feizhu') for use in error logging and database records.

## FeizhuCrawler Implementation

### City Code Mapping

Separate mapping for Feizhu (may differ from Ctrip):

```python
# In src/feizhu_crawler.py
FEIZHU_CITY_MAP = {
    "北京": "PEK", "上海": "SHA", "广州": "CAN", "深圳": "SZX",
    # ... full mapping similar to Ctrip
}
```

### URL Building

Feizhu search URL format requires investigation during implementation.

**Investigation Tasks:**
1. Visit fliggy.com and perform a manual flight search
2. Capture the actual search URL format and parameters
3. Identify required parameters (city codes or city names, date format, passenger count)
4. Test if URL format varies for different routes or dates

**Implementation Approach:**
```python
def _build_search_url(self, from_city: str, to_city: str, date_str: str) -> str:
    # TODO: Determine actual URL format through investigation
    # Example placeholder (to be replaced after investigation):
    return f"https://www.fliggy.com/..."
```

### Parsing

Use Feizhu-specific CSS selectors to parse flight data.

## Database Changes

### Migration Strategy

Add a migration method to handle existing databases:

```python
async def migrate_add_source_column(self) -> None:
    """Migration to add source column to all tables"""
    async with self._get_connection() as db:
        # For existing databases, all data was from Ctrip, so use 'ctrip' as default
        for table in ['price_history', 'low_price_alerts', 'execution_logs']:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN source TEXT DEFAULT 'ctrip'")
                logger.info(f"Added source column to {table}")
            except aiosqlite.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
        # Add indexes for source queries (improves query performance)
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

Call migration in `Database.init()`:

```python
async def init(self) -> None:
    # ... existing initialization ...
    await self.migrate_add_source_column()
```

### Rollback Strategy

If migration causes issues, manual rollback:

```sql
-- Drop the source column
ALTER TABLE price_history DROP COLUMN source;
ALTER TABLE low_price_alerts DROP COLUMN source;
ALTER TABLE execution_logs DROP COLUMN source;

-- Drop the index
DROP INDEX IF EXISTS idx_price_source;
```

**Note:** Rollback will lose any new data with source information. Always backup database before migration:
```bash
cp data/flights.db data/flights.db.backup
```

### Schema Updates

Add `source` column to tables (via migration):

```sql
ALTER TABLE price_history ADD COLUMN source TEXT DEFAULT 'ctrip';
ALTER TABLE low_price_alerts ADD COLUMN source TEXT DEFAULT 'ctrip';
ALTER TABLE execution_logs ADD COLUMN source TEXT DEFAULT 'ctrip';

CREATE INDEX IF NOT EXISTS idx_price_source ON price_history(source);
CREATE INDEX IF NOT EXISTS idx_alert_source ON low_price_alerts(source);
CREATE INDEX IF NOT EXISTS idx_log_source ON execution_logs(source);
```

### API Updates

Update database methods to accept `source` parameter:

```python
async def save_price_history(
    self,
    route_from: str,
    route_to: str,
    flight_date: str,
    flight_no: str,
    airline: str,
    price: int,
    source: str = "ctrip"  # New parameter with default
) -> None:
    ...

async def save_alert(
    self,
    ...
    source: str = "ctrip"  # New parameter with default
) -> None:
    ...

async def log_execution(
    self,
    ...
    source: str = "ctrip"  # New parameter with default
) -> None:
    ...
```

## Notification Changes

Update `src/notifier.py` to include source in alert messages and deduplication.

### Message Templates

**Email:**
```
【飞猪】低价航班提醒

深圳 → 上海 (2026-03-20)
航班: MU5358 (深圳航空)
价格: ¥299
阈值: ¥500

点击查看详情...
```

**Webhook:**
**Decision:** Keep the current text-based format for DingTalk/WeChat compatibility. Add source label to the message content.

**Rationale:** The current webhook implementation uses the `msgtype: text` format required by DingTalk/WeChat APIs. Switching to structured JSON would require:
1. Breaking changes to webhook consumers (they would need to parse JSON instead of reading text)
2. Changes to the webhook payload structure to include proper message format fields
3. Updates to all webhook integration points

Since the current text format works well for notifications and the benefits of JSON don't justify the migration cost, we'll keep the text format with the source label added.

Updated message format:
```
【飞猪】低价航班提醒
深圳 → 上海 (2026-03-20)
航班: MU5358 (深圳航空)
价格: ¥299 (低于阈值 ¥500)
```

**Bark:**
```
【飞猪】深圳→上海 ¥299
MU5358 深圳航空
```

### Deduplication Update

Update `send_low_price_alert()` signature to accept `flight_date` and `threshold` parameters:

```python
async def send_low_price_alert(self, flights: List[Dict[str, Any]], flight_date: date, threshold: int) -> None:
    ...
    alert_id = f"{flight['route_from']}-{flight['route_to']}-{flight_date.isoformat()}-{flight['flight_no']}-{flight['source']}"
```

Call from `main.py`:
```python
await self.notifier.send_low_price_alert(low_price_flights, flight_date, route.low_price_threshold)
```

## Error Handling Strategy

- **No fallback between sources** - If Feizhu crawler fails, log error and continue (no automatic fallback to Ctrip). This design choice ensures users are aware which source is working and can investigate failures directly.
- **Retry logic** - Maintain existing `@retry_with_backoff` decorator for each crawler independently
- **Anti-bot detection** - Each crawler implements its own detection patterns
- **Clear error messages** - Each crawler should include its source name in error logs

**Logging Prefix Implementation:**
Each crawler can use a module-level logger or prefix messages manually:
```python
logger = logging.getLogger(f"src.{self.__class__.__name__}")
# This will produce logs like "[FeizhuCrawler] Connection timeout"
```

Or explicitly prefix critical messages:
```python
logger.error(f"[{self.source}] Connection timeout")
```

## Migration Path for Date Field Removal

The removal of `date` from flight dictionaries is a breaking change in the internal API.

**Step 1: Update CtripCrawler**
- Remove `'date': flight_date.isoformat()` from return value in `_parse_single_flight()`
- Add `'source': 'ctrip'` to return value

**Step 2: Update Notifier**
- Change `send_low_price_alert()` signature to accept `flight_date: date` and `threshold: int` parameters
- Update deduplication key to use `flight_date` parameter instead of `flight['date']`
- Update message templates to include source label (keep webhook in text format for DingTalk/WeChat compatibility)

**Step 3: Update main.py**
- Update database method calls to include `source` parameter:
  ```python
  await self.db.save_price_history(..., source=flight['source'])
  await self.db.save_alert(..., source=flight['source'])
  await self.db.log_execution(..., source=self.crawler.source if hasattr(self.crawler, 'source') else self.config.monitor.default_source)
  ```
- Pass `flight_date` and `threshold` to notifier:
  ```python
  await self.notifier.send_low_price_alert(low_price_flights, flight_date, route.low_price_threshold)
  ```

**Backward Compatibility:**
- The crawler's internal API is private, so external callers won't be affected
- No compatibility layer needed since `main.py` is the only consumer

## Files to Create

1. `src/base_crawler.py` - Abstract base class
2. `src/feizhu_crawler.py` - Feizhu implementation

## Files to Modify

1. `src/crawler.py` - Refactor to inherit from `FlightCrawler`, remove `date` from return dict
2. `src/config.py` - Add `default_source` to `MonitorConfig`, add validation
3. `src/database.py` - Add `source` parameter and migration method
4. `src/notifier.py` - Update message templates and deduplication logic (accept `flight_date` parameter)
5. `main.py` - Add crawler factory logic, pass `flight_date` to notifier
6. `config.example.yaml` - Add `default_source` example

## Testing

1. **Unit tests for base class interface** - Verify `FlightCrawler` ABC contract and `source` attribute requirement
2. **Tests for Feizhu city code mapping** - Coverage of major cities
3. **Integration test** - Run monitor with `default_source: "feizhu"`
4. **Database migration test**
   - Test on empty database (new installation)
   - Test on existing database (upgrade scenario)
   - Verify `source` column defaults to 'ctrip' for existing data
   - Verify all three indexes are created
5. **Database stores source correctly** - Insert flights from both sources, verify storage and retrieval
6. **Notifications include source label** - Test all three channels (email, webhook, bark)
7. **Deduplication test**
   - Same flight from different sources should not deduplicate each other
   - Verify deduplication key format includes source
8. **Rollback test** - Verify manual rollback procedure works correctly
9. **Config validation test** - Test that invalid `default_source` raises `ConfigError`
10. **Backward compatibility test** - Verify main.py correctly passes flight_date and threshold to notifier
11. **Crawler source attribute test** - Verify each crawler has `source` attribute accessible for error logging
