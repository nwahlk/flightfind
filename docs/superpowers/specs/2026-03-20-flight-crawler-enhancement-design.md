# FlightFind 爬虫增强设计文档

## 1. 背景

FlightFind 是一个机票价格监控工具，当前支持携程、飞猪、南航、春秋航空四个数据源。主要问题是反爬风控：

| 数据源 | 状态 | 问题 |
|--------|------|------|
| 携程 | 不可用 | 强风控，无法突破 |
| 飞猪 | 不可用 | 强风控，无法突破 |
| 南航 | 不可用 | 滑块验证无法通过 |
| 春秋 | 可用 | 正常工作 |

## 2. 目标

- **预算约束**：月成本 < 10元
- **查询规模**：4条航线 × 3次/天 = 360次/月
- **数据需求**：实时价格 + 历史价格记录
- **扩展性**：支持后续添加更多航司（东航、深航、吉祥等）

## 3. 技术方案

### 3.1 整体策略

采用**混合方案**：
1. 放弃携程/飞猪（风控太强，成本高）
2. 专注官方航司网站（风控相对宽松）
3. 使用增强反爬技术突破现有障碍

### 3.2 反爬增强技术

| 技术 | 用途 | 实现方式 |
|------|------|----------|
| Playwright Stealth | 隐藏自动化特征 | `playwright-stealth` 插件 |
| 随机指纹 | 每次请求不同的浏览器特征 | Canvas/WebGL/字体随机化 |
| 移动端模拟 | 绕过PC端风控 | 模拟手机浏览器访问移动版站点 |
| 请求间隔 | 避免频率触发 | 随机 30-120 秒间隔 |
| Cookie 持久化 | 减少登录频率 | 保存登录状态到文件 |

### 3.3 数据源规划

| 数据源 | 策略 | 优先级 |
|--------|------|--------|
| 南航 | 改进现有爬虫，尝试移动端 + stealth | P0 |
| 春秋 | 保持现状 | - |
| 东航 | 新增 | P1 |
| 深航 | 新增 | P2 |
| 吉祥 | 新增 | P3 |

## 4. 架构设计

### 4.1 组件结构

```
src/
├── base_crawler.py      # 基类（增强反爬能力）
├── stealth.py           # 新增：反检测工具模块
├── cookie_manager.py    # 新增：Cookie 持久化
├── csair_crawler.py     # 改进：南航爬虫
├── spring_crawler.py    # 保持：春秋爬虫
├── mu_crawler.py        # 新增：东航爬虫
├── zh_crawler.py        # 新增：深航爬虫
└── ho_crawler.py        # 新增：吉祥爬虫
```

### 4.2 BaseCrawler 增强

```python
class FlightCrawler(ABC):
    # 新增属性
    use_stealth: bool = True      # 启用反检测
    mobile_mode: bool = False     # 移动端模式
    cookie_file: Path | None      # Cookie 持久化路径

    # 新增方法
    async def _apply_stealth(self) -> None: ...
    async def _randomize_fingerprint(self) -> None: ...
    async def _load_cookies(self) -> None: ...
    async def _save_cookies(self) -> None: ...
    async def _random_delay(self) -> None: ...
```

### 4.3 Stealth 模块设计

```python
# src/stealth.py

async def apply_stealth_to_page(page: Page) -> None:
    """应用 stealth 模式到页面"""
    # 1. 注入 stealth 脚本
    # 2. 隐藏 webdriver 特征
    # 3. 伪造 plugins/mimeTypes
    # 4. 随机化 canvas 指纹

def get_random_mobile_ua() -> str:
    """获取随机移动端 UA"""

def get_random_desktop_ua() -> str:
    """获取随机桌面端 UA"""
```

### 4.4 Cookie 持久化设计

```python
# src/cookie_manager.py

class CookieManager:
    def __init__(self, cookie_dir: Path):
        self.cookie_dir = cookie_dir

    async def load(self, source: str) -> list[dict] | None:
        """加载指定数据源的 cookies"""

    async def save(self, source: str, cookies: list[dict]) -> None:
        """保存 cookies"""

    async def clear(self, source: str) -> None:
        """清除 cookies"""
```

## 5. 实现计划

### Phase 1: 基础设施增强（预计 2-3 天）

1. **Stealth 模块**
   - 创建 `src/stealth.py`
   - 实现 webdriver 特征隐藏
   - 实现指纹随机化
   - 实现移动端 UA 生成

2. **Cookie 管理器**
   - 创建 `src/cookie_manager.py`
   - 实现 cookies 的加载/保存/清除
   - 集成到 BaseCrawler

3. **BaseCrawler 增强**
   - 添加 stealth 模式支持
   - 添加移动端模式支持
   - 添加随机延迟机制

### Phase 2: 南航爬虫改进（预计 1-2 天）

1. 研究南航移动端接口
2. 集成 stealth 模式
3. 测试滑块绕过
4. 添加降级策略（PC端失败时尝试移动端）

### Phase 3: 新增航司（每个 1-2 天）

按优先级实现：
1. 东航 (ceair.com)
2. 深航 (shenzhenair.com)
3. 吉祥 (juneyaoair.com)

## 6. 风险与应对

| 风险 | 可能性 | 影响 | 应对措施 |
|------|--------|------|----------|
| Stealth 模式仍被检测 | 中 | 南航不可用 | 尝试移动端接口；降低查询频率 |
| 移动端接口也有风控 | 低 | 需要其他方案 | 研究航司小程序接口 |
| 新航司风控严格 | 中 | 部分航司不可用 | 优先实现风控宽松的航司 |

## 7. 验收标准

- [ ] 南航爬虫可稳定获取价格数据
- [ ] 新增至少 2 个航司数据源
- [ ] 所有爬虫支持 Cookie 持久化
- [ ] 查询间隔随机化，避免触发风控
- [ ] 月运行成本 < 10元
