# Airport Information Implementation Plan

## Overview

Add departure airport and arrival airport information for single-trip flights. Airport codes captured from crawler pages (Feizhu: `.css里flight-port`, `.flight-port`; Ctrip similar selectors) are translated to actual airport names in notifications.

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add departure and arrival airport information to flight data structure with code-to-name mapping for notification display.

**Architecture:** Extend existing flight data format with `departure_airport` and `arrival_airport` fields. Update database schema, crawler parsing, and notification templates.

**Tech Stack:** Python 3.12+, Playwright, aiosqlite, pytest

---

## File Structure

```
src/
├── base_crawler.py              [NO CHANGE]
├── crawler.py                [MODIFY] Add airport parsing
├── feizhu_crawler.py          [MODIFY] Add airport parsing
├── config.py                 [MODIFY] Add AIRPORT_NAMES mapping
├── database.py                [MODIFY] Add airport columns, migration, API updates
├── notifier.py                [MODIFY] Update message templates with airport names
└── __init__.py               [NO CHANGE]

config.example.yaml               [NO CHANGE]
docs/superpowers/specs/         [NO CHANGE]
docs/superpowers/plans/          [NEW] This file
```

---

## Task 1: Add Airport Name Mapping

**Files:**
- Create or modify: `src/config.py`

**Steps:**
1. Add AIRPORT_NAMES constant with Chinese airport names
2. Add get_airport_name() helper function
3. Commit

**Implementation:**
```python
# 在 config.py 或 crawler 模块中添加
AIRPORT_NAMES = {
    'PEK': '北京首都', 'PKX': '大兴',
    'SHA': '虹桥', 'PVG': '浦东',
    'CAN': '白云', 'SZX': '宝安',
    # ... 完整映射
}

def get_airport_name(airport_code: str) -> str:
    """获取机场名称"""
    return AIRPORT_NAMES.get(airport_code, airport_code)  # 映射或使用机场代码本身
```

---

## Task 2: Update Crawler Parsing

**Files:**
- Modify: `src/crawler.py`
- Modify: `src/feizhu_crawler.py`

**Steps:**
1. Update `_parse_single_flight()` to parse departure_airport and arrival_airport
2. Commit

**Implementation for Ctrip:**
```python
# 在 _parse_single_flight() 方法中添加
departure_airport = await self._get_text(item, ['.flight-port', '[data-flight-port]'])
arrival_airport = await self._get_text(item, ['.arrival-port', '[data-arrival-port]'))
```

**Implementation for Feizhu:**
```python
# 在 _parse_single_flight() 方法中添加
departure_airport = await self._get_text(item, ['.css里flight-port'])
arrival_airport = await self._get_text(item, ['port-arr'])
```

---

## Task 3: Database Migration

**Files:**
- Modify: `src/database.py`

**Steps:**
1. Add `migrate_add_airport_columns()` method
2. Call migration in `init()`
3. Commit

**Implementation:**
```python
async def migrate_add_airport_columns(self) -> None:
    """迁移机场列"""
    async with self._get_connection() as db:
        for table in ['price_history', 'low_price_alerts']:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN departure_airport TEXT DEFAULT ''")
                await db.execute(f"ALTER TABLE {table} ADD COLUMN arrival_airport TEXT DEFAULT ''")
                logger.info(f"Added airport columns to {table}")
            except aiosqlite.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
        await db.commit()
```

---

## Task 4: Update Database API

**Files:**
- Modify: `src/database.py`

**Steps:**
1. Update `save_price_history()` to accept airport parameters
2. Update `save_alert()` to accept airport parameters
3. Commit

**Implementation:**
```python
# save_price_history 添加参数
async def save_price_history(
    self,
    route_from: str,
    route_to: str,
    flight_date: str,
    flight_no: str,
    airline: str,
    price: int,
    departure_airport: str = '',  # 新增
    arrival_airport: str = '',      # 新增
    source: str = "ctrip"
) -> None:
    sql = """
        INSERT INTO price_history
        (route_from, route_to, flight_date, flight_no, airline, price, departure_airport, arrival_airport, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    await db.execute(sql, (...))

# save_alert 添加参数
async def save_alert(
    self,
    route_from: str,
    route_to: str,
    flight_date: str,
    flight_no: str,
    airline: str,
    price: int,
    threshold: int,
    departure_airport: str = '',  # 新增
    arrival_airport: str = '',      # 新增
    source: str = "ctrip",
    channels: str = ""
) -> None:
    sql = """
        INSERT INTO low_price_alerts
        (route_from, route_to, flight_date, flight_no, airline, price, threshold, departure_airport, arrival_airport, source, channels)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    await db.execute(sql, (...))
```

---

## Task 5: Update Notification Templates

**Files:**
- Modify: `src/notifier.py`

**Steps:**
1. Update `_send_single_alert()` to include airport information
2. Update email template
3. Commit

**Implementation:**
```python
# _send_single_alert 添加机场信息
departure_name = get_airport_name(flight.get('departure_airport', ''))
arrival_name = get_airport_name(flight.get('arrival_airport', ''))

departure_part = f"出发：{departure_name}" if departure_name else ""
arrival_part = f"到达：{arrival_name}" if arrival_name else ""

route_info = f"{flight.get('route_from', '')}({departure_part}) → {flight.get('route_to', '')}({arrival_part})"

# Email body 更新
body = f"""
{route_info} ({flight_date})
航班: {flight['flight_no']} ({flight['airline']})
价格: ¥{flight['price']}
{departure_part}
{arrival_part}
"""

# Webhook content 更新
content = f"""{title}
{route_info} ({flight_date})
航班: {flight['flight_no']} ({flight['airline']})
价格: ¥{flight['price']}
{departure_part}
{arrival_part}
"""
```

---

## Task 6: Integration Testing

**Steps:**
1. Run monitor and verify airport info is captured
2. Check database columns exist
3. Verify notification messages show airport names
4. Commit test config changes

---

## Summary Checklist

- [ ] Task 1: Add airport name mapping
- [ ] Task 2: Update crawler parsing for airports
- [ ] Task 3: Database migration
- [ ] Task 4: Database API updates
- [ ] Task 5: Notification template updates
- [ ] Task 6: Integration testing