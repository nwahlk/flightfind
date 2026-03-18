# Airport Information for Flights Design

## Overview

Add departure airport and arrival airport information for single-trip flights. Airport codes captured from crawler pages (using CSS selectors) are translated to actual airport names in notifications for better user experience.

## Architecture

### Data Format

All crawlers must return flights with airport information:

```python
{
    'flight_no': str,      # 航班号
    'airline': str,        # 航空公司
    'price': int,          # 价格（整数）
    'route_from': str,     # 出发城市
    'route_to': str,       # 目的城市
    'source': str,          # 数据源，"ctrip" 或 "feizhu"
    'departure_airport': str,  # 新增：出发机场代码（如 PEK, SHA）
    'arrival_airport': str,       # 新增：到达机场代码（如 PVG, SHA）
    'date': str            # 日期
}
```

### Airport Name Mapping

```python
AIRPORT_NAMES = {
    'PEK': '北京首都',   # Beijing Capital
    'PKX': '大兴',     # Beijing Daxing
    'SHA': '虹桥',     # Shanghai Hongqiao
    'PVG': '浦东',     # Shanghai Pudong
    'CAN': '白云',     # Guangzhou Baiyun
    'SZX': '宝安',     # Shenzhen Bao'an
    'CTU': '双流',     # Chengdu Shuangliu
    'KMG': '长水',     # Kunming Changshui
    'XIY': '咸阳',     # Xi'an Xianyang
    'CKG': '江北',     # Chongqing Jiangbei
    'TAO': '胶东',     # Qingdao Jiaodong
    'TSN': '滨海',     # Tianjin Binhai
    'DLC': '周水子',   # Dalian Zhoushuizi
    'XMN': '高崎',     # Xiamen Gaoqi
    'HGH': '萧山',     # Hangzhou Xiaoshan
    'WUH': '天河',     # Wuhan Tianhe
    'NKG': '禄口',     # Nanjing Lukou
    'CSX': '遥墙',     # Changsha Huanghua
    'CGO': '新郑',     # Zhengzhou Xinzheng
    'HET': '白塔',     # Hohhot Baita
    'SHE': '正定',     # Shijiazhuang
    'URC': '地窝铺',     # Urumqi Diwopu
    'INC': '河东',     # Yinchuan Hedong
    'KWL': '两江',     # Guilin Liangjiang
    'FOC': '长乐',     # Fuzhou Changle
    'SYX': '凤凰',     # Sanya Fenghuang
    'HAK': '美兰',     # Haikou Meilan
    'HFE': '新桥',     # Hefei Xinqiao
    'KHN': '昌北',     # Nanchang Changbei
    'LJG': '三义',     # Lijiang Sanyi
}
```

### Airport Name Helper

```python
def get_airport_name(airport_code: str) -> str:
    """获取机场名称"""
    return AIRPORT_NAMES.get(airport_code, airport_code)  # 代码映射或使用机场代码本身
```

## CSS Selectors

| Element | Feizhu | Ctrip |
|---------|--------|-------|
| 出发机场 | `.css里flight-port` | `.flight-port` |
| 到达机场 | `port-arr` | `.arrival-port` |
| 航班号 | `[data-flight-no]` | `.flight-number` |
| 航空公司 | `[data-airline]` | `.airline` |

## Database Changes

### Schema Updates

Add `departure_airport` and `arrival_airport` columns to tables:

```sql
ALTER TABLE price_history ADD COLUMN departure_airport TEXT DEFAULT '';
ALTER TABLE price_history ADD COLUMN arrival_airport TEXT DEFAULT '';

ALTER TABLE low_price_alerts ADD COLUMN departure_airport TEXT DEFAULT '';
ALTER TABLE low_price_alerts ADD COLUMN arrival_airport TEXT DEFAULT '';
```

### API Updates

Update database methods to accept airport parameters:

```python
async def save_price_history(
    self,
    route_from: str,
    route_to: str,
    flight_date: str,
    flight_no: str,
    airline: str,
    price: int,
    departure_airport: str = '',  # 新增：出发机场代码
    arrival_airport: str = '',      # 新增：到达机场代码
    source: str = 'ctrip'
) -> None:
    ...

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
    source: str = 'ctrip',
    channels: str = ''
) -> None:
    ...
```

## Notification Changes

Update notification templates to show airport names instead of codes.

### Message Template

```
【飞猪】深圳(宝安) → 上海(浦东) (2026-04-03)
航班: MU5358 (深圳航空)
价格: ¥299
出发：宝安机场
到达：浦东机场
```

### Template Logic

```python
departure_name = get_airport_name(flight.get('departure_airport', ''))
arrival_name = get_airport_name(flight.get('arrival_airport', ''))

departure_part = f"出发：{departure_name}" if departure_name else ""
arrival_part = f"到达：{arrival_name}" if arrival_name else ""

# 在 route 信息中
route_info = f"{flight['route_from']}({departure_part}) → {flight['route_to']}({arrival_part})"
```

## Files to Modify

1. `src/crawler.py` - Add departure/arrival airport parsing
2. `src/feizhu_crawler.py` - Add departure/arrival airport parsing
3. `src/config.py` - Add AIRPORT_NAMES mapping (optional, could be in crawler utils)
4. `src/database.py` - Add migration for airport columns, update API methods
5. `src/notifier.py` - Update message templates with airport names

## Testing

1. Unit tests for airport name mapping
2. Integration test - Run monitor, verify airport info is captured and stored correctly
3. Notification test - Verify airport names appear in alerts