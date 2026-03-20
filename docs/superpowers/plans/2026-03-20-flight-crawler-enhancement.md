# FlightFind 爬虫增强实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增强 FlightFind 的反爬能力，改进南航爬虫，并新增东航、深航、吉祥三个数据源

**Architecture:** 采用混合方案，在现有 BaseCrawler 基础上增加 stealth 模块和 cookie 持久化，保持各航司爬虫独立实现

**Tech Stack:** Python 3.10+, Playwright, aiosqlite, asyncio

---

## 文件结构

```
src/
├── base_crawler.py      # 修改：增加 stealth 和 cookie 支持
├── stealth.py           # 新增：反检测模块
├── cookie_manager.py    # 新增：Cookie 持久化管理
├── csair_crawler.py     # 修改：集成新的 stealth 模块
├── mu_crawler.py        # 新增：东航爬虫
├── zh_crawler.py        # 新增：深航爬虫
└── ho_crawler.py        # 新增：吉祥爬虫

tests/
├── test_stealth.py      # 新增：stealth 模块测试
├── test_cookie_manager.py  # 新增：cookie 管理器测试
├── test_mu_crawler.py   # 新增：东航爬虫测试
├── test_zh_crawler.py   # 新增：深航爬虫测试
└── test_ho_crawler.py   # 新增：吉祥爬虫测试
```

---

## Task 1: Stealth 反检测模块

**Files:**
- Create: `src/stealth.py`
- Test: `tests/test_stealth.py`

### Step 1.1: 编写 stealth 模块测试

- [ ] **创建测试文件**

```python
# tests/test_stealth.py
import pytest
from src.stealth import (
    get_random_mobile_ua,
    get_random_desktop_ua,
    get_stealth_init_script,
    get_random_viewport,
)


def test_get_random_mobile_ua():
    """测试获取随机移动端 UA"""
    ua = get_random_mobile_ua()
    assert isinstance(ua, str)
    assert len(ua) > 50
    assert "Mobile" in ua or "Android" in ua or "iPhone" in ua


def test_get_random_desktop_ua():
    """测试获取随机桌面端 UA"""
    ua = get_random_desktop_ua()
    assert isinstance(ua, str)
    assert len(ua) > 50
    assert "Windows" in ua or "Macintosh" in ua


def test_get_stealth_init_script():
    """测试获取 stealth 初始化脚本"""
    script = get_stealth_init_script()
    assert isinstance(script, str)
    assert len(script) > 100
    assert "webdriver" in script


def test_get_random_viewport():
    """测试获取随机视口尺寸"""
    viewport = get_random_viewport(mobile=False)
    assert "width" in viewport
    assert "height" in viewport
    assert viewport["width"] >= 1200
    assert viewport["height"] >= 800

    viewport_mobile = get_random_viewport(mobile=True)
    assert viewport_mobile["width"] < 500
```

- [ ] **运行测试验证失败**

```bash
pytest tests/test_stealth.py -v
```

Expected: FAIL - 模块不存在

### Step 1.2: 实现 stealth 模块

- [ ] **创建 stealth 模块**

```python
# src/stealth.py
"""
反检测工具模块，提供浏览器指纹伪装和反自动化检测功能。
"""

import random
from typing import Dict


# 移动端 User-Agent 池
MOBILE_USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Xiaomi 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
]

# 桌面端 User-Agent 池
DESKTOP_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def get_random_mobile_ua() -> str:
    """获取随机移动端 User-Agent"""
    return random.choice(MOBILE_USER_AGENTS)


def get_random_desktop_ua() -> str:
    """获取随机桌面端 User-Agent"""
    return random.choice(DESKTOP_USER_AGENTS)


def get_random_viewport(mobile: bool = False) -> Dict[str, int]:
    """获取随机视口尺寸

    Args:
        mobile: 是否为移动端

    Returns:
        包含 width 和 height 的字典
    """
    if mobile:
        viewports = [
            {"width": 375, "height": 812},   # iPhone X
            {"width": 390, "height": 844},   # iPhone 12/13
            {"width": 393, "height": 852},   # iPhone 14
            {"width": 360, "height": 800},   # Android
            {"width": 412, "height": 915},   # Pixel
        ]
    else:
        viewports = [
            {"width": 1920, "height": 1080},
            {"width": 1440, "height": 900},
            {"width": 1536, "height": 864},
            {"width": 1366, "height": 768},
            {"width": 1600, "height": 900},
        ]
    return random.choice(viewports)


def get_stealth_init_script() -> str:
    """获取 stealth 初始化脚本

    返回用于注入页面的 JavaScript 代码，用于隐藏自动化特征。
    """
    return """
    // 隐藏 webdriver 属性
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined
    });
    delete navigator.__proto__.webdriver;

    // 伪造 plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
        ]
    });

    // 伪造语言
    Object.defineProperty(navigator, 'languages', {
        get: () => ['zh-CN', 'zh', 'en-US', 'en']
    });

    // 伪造平台
    Object.defineProperty(navigator, 'platform', {
        get: () => 'Win32'
    });

    // 伪造硬件信息
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => 8
    });
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => 8
    });
    Object.defineProperty(navigator, 'maxTouchPoints', {
        get: () => 0
    });

    // 添加 Chrome 对象
    window.chrome = {
        runtime: { id: undefined },
        loadTimes: function() {},
        csi: function() {},
        app: {
            isInstalled: false,
            InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
            RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
        }
    };

    // 伪造权限 API
    const _origQuery = window.navigator.permissions.query.bind(navigator.permissions);
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : _origQuery(parameters);

    // WebGL 指纹伪装
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel(R) UHD Graphics 630';
        return getParameter.call(this, parameter);
    };

    // Canvas 指纹噪声
    const getImageData = CanvasRenderingContext2D.prototype.getImageData;
    CanvasRenderingContext2D.prototype.getImageData = function() {
        const imageData = getImageData.apply(this, arguments);
        for (let i = 0; i < imageData.data.length; i += 4) {
            imageData.data[i] += Math.floor(Math.random() * 3) - 1;
        }
        return imageData;
    };

    // 伪造连接信息
    Object.defineProperty(navigator, 'connection', {
        get: () => ({
            effectiveType: '4g',
            rtt: 50,
            downlink: 10,
            saveData: false,
            addEventListener: () => {},
            removeEventListener: () => {}
        })
    });
    """
```

- [ ] **运行测试验证通过**

```bash
pytest tests/test_stealth.py -v
```

Expected: PASS

### Step 1.3: 提交

```bash
git add src/stealth.py tests/test_stealth.py
git commit -m "feat: add stealth module for anti-detection"
```

---

## Task 2: Cookie 持久化管理器

**Files:**
- Create: `src/cookie_manager.py`
- Test: `tests/test_cookie_manager.py`

### Step 2.1: 编写 cookie 管理器测试

- [ ] **创建测试文件**

```python
# tests/test_cookie_manager.py
import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from src.cookie_manager import CookieManager


@pytest.fixture
def temp_cookie_dir():
    """创建临时目录用于存储 cookie"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.mark.asyncio
async def test_cookie_manager_init(temp_cookie_dir):
    """测试 CookieManager 初始化"""
    manager = CookieManager(temp_cookie_dir)
    assert manager.cookie_dir == temp_cookie_dir


@pytest.mark.asyncio
async def test_save_and_load_cookies(temp_cookie_dir):
    """测试保存和加载 cookies"""
    manager = CookieManager(temp_cookie_dir)

    cookies = [
        {"name": "session", "value": "test123", "domain": "example.com"},
        {"name": "token", "value": "abc456", "domain": "example.com"},
    ]

    # 保存 cookies
    await manager.save_cookies("test_site", cookies)

    # 加载 cookies
    loaded = await manager.load_cookies("test_site")
    assert len(loaded) == 2
    assert loaded[0]["name"] == "session"
    assert loaded[1]["name"] == "token"


@pytest.mark.asyncio
async def test_load_nonexistent_cookies(temp_cookie_dir):
    """测试加载不存在的 cookies"""
    manager = CookieManager(temp_cookie_dir)
    loaded = await manager.load_cookies("nonexistent")
    assert loaded == []


@pytest.mark.asyncio
async def test_clear_cookies(temp_cookie_dir):
    """测试清除 cookies"""
    manager = CookieManager(temp_cookie_dir)

    cookies = [{"name": "session", "value": "test123", "domain": "example.com"}]
    await manager.save_cookies("test_site", cookies)

    # 清除
    await manager.clear_cookies("test_site")

    # 验证已清除
    loaded = await manager.load_cookies("test_site")
    assert loaded == []
```

- [ ] **运行测试验证失败**

```bash
pytest tests/test_cookie_manager.py -v
```

Expected: FAIL - 模块不存在

### Step 2.2: 实现 cookie 管理器

- [ ] **创建 cookie 管理器模块**

```python
# src/cookie_manager.py
"""
Cookie 持久化管理器，用于保存和恢复浏览器 cookies。
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class CookieManager:
    """管理浏览器 cookies 的持久化存储"""

    def __init__(self, cookie_dir: Path):
        """初始化 Cookie 管理器

        Args:
            cookie_dir: cookie 文件存储目录
        """
        self.cookie_dir = Path(cookie_dir)
        self.cookie_dir.mkdir(parents=True, exist_ok=True)

    def _get_cookie_path(self, site_name: str) -> Path:
        """获取指定站点的 cookie 文件路径"""
        safe_name = site_name.replace("/", "_").replace("\\", "_")
        return self.cookie_dir / f"{safe_name}_cookies.json"

    async def save_cookies(self, site_name: str, cookies: List[Dict[str, Any]]) -> None:
        """保存 cookies 到文件

        Args:
            site_name: 站点标识名称
            cookies: cookie 列表
        """
        if not cookies:
            logger.debug("No cookies to save for %s", site_name)
            return

        cookie_path = self._get_cookie_path(site_name)
        try:
            cookie_path.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.info("Saved %d cookies for %s", len(cookies), site_name)
        except Exception as exc:
            logger.warning("Failed to save cookies for %s: %s", site_name, exc)

    async def load_cookies(self, site_name: str) -> List[Dict[str, Any]]:
        """从文件加载 cookies

        Args:
            site_name: 站点标识名称

        Returns:
            cookie 列表，如果文件不存在则返回空列表
        """
        cookie_path = self._get_cookie_path(site_name)
        if not cookie_path.exists():
            logger.debug("No cookie file found for %s", site_name)
            return []

        try:
            content = cookie_path.read_text(encoding="utf-8")
            cookies = json.loads(content)
            logger.info("Loaded %d cookies for %s", len(cookies), site_name)
            return cookies
        except json.JSONDecodeError as exc:
            logger.warning("Invalid cookie file for %s: %s", site_name, exc)
            return []
        except Exception as exc:
            logger.warning("Failed to load cookies for %s: %s", site_name, exc)
            return []

    async def clear_cookies(self, site_name: str) -> None:
        """清除指定站点的 cookies

        Args:
            site_name: 站点标识名称
        """
        cookie_path = self._get_cookie_path(site_name)
        if cookie_path.exists():
            try:
                cookie_path.unlink()
                logger.info("Cleared cookies for %s", site_name)
            except Exception as exc:
                logger.warning("Failed to clear cookies for %s: %s", site_name, exc)
```

- [ ] **运行测试验证通过**

```bash
pytest tests/test_cookie_manager.py -v
```

Expected: PASS

### Step 2.3: 提交

```bash
git add src/cookie_manager.py tests/test_cookie_manager.py
git commit -m "feat: add cookie manager for persistent storage"
```

---

## Task 3: 增强 BaseCrawler

**Files:**
- Modify: `src/base_crawler.py`
- Test: `tests/test_base_crawler.py`

### Step 3.1: 增强 BaseCrawler 类

- [ ] **修改 BaseCrawler，添加 stealth 和 cookie 支持**

```python
# src/base_crawler.py
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional
import asyncio
import random
import logging

from src.config import Route
from src.stealth import get_stealth_init_script, get_random_desktop_ua, get_random_viewport
from src.cookie_manager import CookieManager

logger = logging.getLogger(__name__)


class FlightCrawler(ABC):
    """Abstract base class for all flight crawlers with anti-detection support."""

    source: str

    def __init__(
        self,
        headless: bool = True,
        use_stealth: bool = True,
        mobile_mode: bool = False,
        cookie_dir: Optional[Path] = None,
    ):
        """Initialize crawler with anti-detection options.

        Args:
            headless: 是否无头模式运行
            use_stealth: 是否启用反检测模式
            mobile_mode: 是否模拟移动端
            cookie_dir: cookie 存储目录
        """
        self.headless = headless
        self.use_stealth = use_stealth
        self.mobile_mode = mobile_mode
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None

        # Cookie 管理器
        if cookie_dir:
            self.cookie_manager = CookieManager(cookie_dir)
        else:
            self.cookie_manager = None

    async def _apply_stealth_to_context(self) -> None:
        """Apply stealth settings to browser context."""
        if not self.context or not self.use_stealth:
            return

        await self.context.add_init_script(get_stealth_init_script())
        logger.info("[%s] Stealth mode applied", self.source)

    async def _load_cookies_to_context(self) -> None:
        """Load saved cookies into browser context."""
        if not self.context or not self.cookie_manager:
            return

        cookies = await self.cookie_manager.load_cookies(self.source)
        if cookies:
            await self.context.add_cookies(cookies)
            logger.info("[%s] Loaded %d cookies", self.source, len(cookies))

    async def _save_cookies_from_context(self) -> None:
        """Save cookies from browser context."""
        if not self.context or not self.cookie_manager:
            return

        try:
            cookies = await self.context.cookies()
            await self.cookie_manager.save_cookies(self.source, cookies)
        except Exception as exc:
            logger.warning("[%s] Failed to save cookies: %s", self.source, exc)

    async def _random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """随机延迟，模拟人类操作间隔"""
        await asyncio.sleep(random.uniform(min_seconds, max_seconds))

    def _get_browser_args(self) -> List[str]:
        """获取浏览器启动参数"""
        return [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-extensions",
            "--disable-gpu",
        ]

    def _get_context_options(self) -> Dict[str, Any]:
        """获取浏览器上下文选项"""
        viewport = get_random_viewport(mobile=self.mobile_mode)
        ua = get_random_desktop_ua()

        return {
            "viewport": viewport,
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "user_agent": ua,
            "extra_http_headers": {
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        }

    @abstractmethod
    async def init(self) -> None:
        """Initialize browser resources."""

    @abstractmethod
    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        """Search flights and return normalized records."""

    @abstractmethod
    async def close(self) -> None:
        """Release crawler resources."""
```

- [ ] **更新测试**

```python
# tests/test_base_crawler.py
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from src.base_crawler import FlightCrawler


class ConcreteCrawler(FlightCrawler):
    """用于测试的具体爬虫实现"""

    source = "test"

    async def init(self):
        pass

    async def search_flights(self, route):
        return []

    async def close(self):
        pass


def test_crawler_default_options():
    """测试默认选项"""
    crawler = ConcreteCrawler()
    assert crawler.headless is True
    assert crawler.use_stealth is True
    assert crawler.mobile_mode is False
    assert crawler.cookie_manager is None


def test_crawler_custom_options():
    """测试自定义选项"""
    crawler = ConcreteCrawler(
        headless=False,
        use_stealth=False,
        mobile_mode=True,
        cookie_dir=Path("/tmp/cookies"),
    )
    assert crawler.headless is False
    assert crawler.use_stealth is False
    assert crawler.mobile_mode is True
    assert crawler.cookie_manager is not None


def test_get_browser_args():
    """测试获取浏览器参数"""
    crawler = ConcreteCrawler()
    args = crawler._get_browser_args()
    assert "--no-sandbox" in args
    assert "--disable-blink-features=AutomationControlled" in args


def test_get_context_options():
    """测试获取上下文选项"""
    crawler = ConcreteCrawler()
    options = crawler._get_context_options()
    assert "viewport" in options
    assert "user_agent" in options
    assert "zh-CN" in options["locale"]


@pytest.mark.asyncio
async def test_random_delay():
    """测试随机延迟"""
    crawler = ConcreteCrawler()
    import time
    start = time.time()
    await crawler._random_delay(0.1, 0.2)
    elapsed = time.time() - start
    assert 0.1 <= elapsed <= 0.3  # 允许一些误差


def test_cannot_instantiate_base_class():
    """Cannot instantiate abstract class"""
    with pytest.raises(TypeError):
        crawler = FlightCrawler()
```

- [ ] **运行测试验证通过**

```bash
pytest tests/test_base_crawler.py -v
```

Expected: PASS

### Step 3.2: 提交

```bash
git add src/base_crawler.py tests/test_base_crawler.py
git commit -m "feat: enhance BaseCrawler with stealth and cookie support"
```

---

## Task 4: 改进南航爬虫

**Files:**
- Modify: `src/csair_crawler.py`

### Step 4.1: 集成新的 stealth 模块

- [ ] **修改南航爬虫，使用新的 stealth 和 cookie 功能**

主要修改点：
1. 继承新的 BaseCrawler 选项
2. 使用 CookieManager 持久化登录状态
3. 简化 init() 方法中的反检测代码（使用 stealth 模块）
4. 添加移动端降级策略

```python
# 在 CsairCrawler.__init__ 中添加 cookie 支持
def __init__(self, headless: bool = True, cookie_dir: Path = None):
    super().__init__(
        headless=headless,
        use_stealth=True,
        mobile_mode=False,
        cookie_dir=cookie_dir or Path("data/cookies"),
    )
    # ... 其他初始化代码保持不变
```

```python
# 简化 init() 方法
async def init(self) -> None:
    try:
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=self._get_browser_args(),  # 使用基类方法
        )
        options = self._get_context_options()  # 使用基类方法
        self.context = await self.browser.new_context(**options)
        await self._apply_stealth_to_context()  # 使用基类方法
        await self._load_cookies_to_context()   # 使用基类方法
    except Exception as exc:
        raise BrowserCrashError(f"csair browser init failed: {exc}") from exc
```

```python
# 在 close() 方法中保存 cookies
async def close(self) -> None:
    await self._save_cookies_from_context()  # 保存 cookies
    if self.context:
        await self.context.close()
        self.context = None
    if self.browser:
        await self.browser.close()
        self.browser = None
    if self.playwright:
        await self.playwright.stop()
        self.playwright = None
```

- [ ] **测试南航爬虫**

```bash
pytest tests/ -k csair -v
```

### Step 4.2: 提交

```bash
git add src/csair_crawler.py
git commit -m "refactor: integrate stealth module into CsairCrawler"
```

---

## Task 5: 新增东航爬虫

**Files:**
- Create: `src/mu_crawler.py`
- Test: `tests/test_mu_crawler.py`

### Step 5.1: 编写东航爬虫测试

- [ ] **创建测试文件**

```python
# tests/test_mu_crawler.py
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from src.mu_crawler import MuCrawler, get_mu_city_code


def test_get_mu_city_code():
    """测试城市代码转换"""
    assert get_mu_city_code("北京") == "BJS"
    assert get_mu_city_code("上海") == "SHA"
    assert get_mu_city_code("深圳") == "SZX"
    assert get_mu_city_code("未知城市") == "未知城市"


@pytest.mark.asyncio
async def test_mu_crawler_init():
    """测试东航爬虫初始化"""
    crawler = MuCrawler(headless=True)
    assert crawler.source == "mu"
    assert crawler.headless is True
```

- [ ] **运行测试验证失败**

```bash
pytest tests/test_mu_crawler.py -v
```

Expected: FAIL - 模块不存在

### Step 5.2: 实现东航爬虫

- [ ] **创建东航爬虫**

```python
# src/mu_crawler.py
"""
China Eastern Airlines (东方航空) official-site crawler.
"""

import asyncio
import json
import logging
import random
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlencode

from playwright.async_api import ElementHandle, Page, async_playwright

from src.base_crawler import FlightCrawler
from src.config import Route
from src.exceptions import BrowserCrashError, CrawlerError, ParseError
from src.flight_record import normalize_flight_record
from src.utils import retry_with_backoff

logger = logging.getLogger(__name__)


MU_CITY_CODE_MAP = {
    "北京": "BJS",
    "上海": "SHA",
    "广州": "CAN",
    "深圳": "SZX",
    "成都": "CTU",
    "杭州": "HGH",
    "西安": "XIY",
    "重庆": "CKG",
    "南京": "NKG",
    "武汉": "WUH",
    "天津": "TSN",
    "青岛": "TAO",
    "大连": "DLC",
    "厦门": "XMN",
    "昆明": "KMG",
    "长沙": "CSX",
    "郑州": "CGO",
    "沈阳": "SHE",
    "济南": "TNA",
    "哈尔滨": "HRB",
    "三亚": "SYX",
    "海口": "HAK",
    "福州": "FOC",
    "南宁": "NNG",
}

MU_AIRLINE_NAME = "东方航空"
MU_HOMEPAGE_URL = "https://www.ceair.com/"


def get_mu_city_code(city_name: str) -> str:
    """获取东航城市代码"""
    return MU_CITY_CODE_MAP.get(city_name, city_name)


class MuCrawler(FlightCrawler):
    """东方航空爬虫"""

    source = "mu"

    def __init__(self, headless: bool = True, cookie_dir: Path = None):
        super().__init__(
            headless=headless,
            use_stealth=True,
            mobile_mode=False,
            cookie_dir=cookie_dir or Path("data/cookies"),
        )
        self.playwright = None
        self.debug_path = Path("logs")
        self.debug_path.mkdir(parents=True, exist_ok=True)
        self._session_warmed = False

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    async def init(self) -> None:
        try:
            from playwright.async_api import async_playwright
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=self._get_browser_args(),
            )
            options = self._get_context_options()
            self.context = await self.browser.new_context(**options)
            await self._apply_stealth_to_context()
            await self._load_cookies_to_context()
        except Exception as exc:
            raise BrowserCrashError(f"mu browser init failed: {exc}") from exc

    @retry_with_backoff(max_attempts=3, base_delay=4.0)
    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        """搜索航班"""
        results: List[Dict[str, Any]] = []
        for index, flight_date in enumerate(sorted(route.dates.absolute_dates)):
            if index:
                await self._random_delay(8.0, 14.0)
            try:
                flights = await self._search_single_date(route, flight_date)
                results.extend(flights)
            except Exception as exc:
                logger.error(
                    "[mu] search failed for %s -> %s on %s: %s",
                    route.from_city, route.to_city, flight_date, exc
                )
        return results

    async def _search_single_date(self, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        """搜索单个日期的航班"""
        if not self.context:
            raise CrawlerError("mu browser context is not initialized")

        await self._warm_session()
        page = await self.context.new_page()

        try:
            url = self._build_search_url(route, flight_date)
            await self._random_delay(1.5, 3.0)
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(random.randint(5000, 8000))

            # 检查是否有反爬
            if await self._check_antibot(page):
                raise CrawlerError("mu page shows anti-bot detection")

            flights = await self._parse_flights(page, route, flight_date)
            await self._save_debug_snapshot(page, route, flight_date, "page")

            if not flights:
                raise ParseError("mu page did not yield any flights")

            return flights
        finally:
            await page.close()

    def _build_search_url(self, route: Route, flight_date: date) -> str:
        """构建搜索 URL"""
        from_code = get_mu_city_code(route.from_city)
        to_code = get_mu_city_code(route.to_city)
        # 东航搜索 URL 格式（需要根据实际网站调整）
        return f"https://www.ceair.com/booking/{from_code}-{to_code}-{flight_date.strftime('%Y%m%d')}/"

    async def _warm_session(self) -> None:
        """预热会话"""
        if self._session_warmed or not self.context:
            return

        page = await self.context.new_page()
        try:
            await page.goto(MU_HOMEPAGE_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(random.randint(3000, 5000))
            self._session_warmed = True
        except Exception as exc:
            logger.info("[mu] warm-up page skipped: %s", exc)
        finally:
            await page.close()

    async def _check_antibot(self, page: Page) -> bool:
        """检查是否有反爬检测"""
        try:
            title = await page.title()
            body = await page.locator("body").inner_text()
            signals = ["验证", "captcha", "拦截", "禁止访问", "Too Many Requests"]
            haystack = f"{title}\n{body}"
            return any(signal in haystack for signal in signals)
        except Exception:
            return False

    async def _parse_flights(self, page: Page, route: Route, flight_date: date) -> List[Dict[str, Any]]:
        """解析航班列表"""
        # 东航页面的航班项选择器（需要根据实际页面调整）
        selectors = [
            ".flight-item",
            "[class*='flight']",
            ".flight-list li",
        ]

        items: List[ElementHandle] = []
        for selector in selectors:
            try:
                items = await page.query_selector_all(selector)
                if items:
                    logger.info("[mu] found %s flight items via %s", len(items), selector)
                    break
            except Exception:
                continue

        flights: List[Dict[str, Any]] = []
        seen = set()

        for item in items:
            flight = await self._parse_single_flight(item, route, flight_date)
            if not flight:
                continue
            key = (flight["flight_no"], flight["price"])
            if key in seen:
                continue
            seen.add(key)
            flights.append(flight)

        return flights

    async def _parse_single_flight(
        self, item: ElementHandle, route: Route, flight_date: date
    ) -> Dict[str, Any] | None:
        """解析单个航班信息"""
        try:
            text = await item.inner_text()
            if not text or len(text) < 10:
                return None

            # 提取航班号
            flight_match = re.search(r"\b(MU\d{3,4})\b", text, re.IGNORECASE)
            if not flight_match:
                return None
            flight_no = flight_match.group(1).upper()

            # 提取价格
            price_match = re.search(r"[¥￥]?\s*(\d{2,5})", text)
            if not price_match:
                return None
            price = int(price_match.group(1))
            if price < 10:
                return None

            return normalize_flight_record(
                route_from=route.from_city,
                route_to=route.to_city,
                flight_date=flight_date,
                flight_no=flight_no,
                airline=MU_AIRLINE_NAME,
                price=price,
                source=self.source,
                metadata={"record_type": "flight_list_page"},
            )
        except Exception:
            return None

    async def _save_debug_snapshot(
        self, page: Page, route: Route, flight_date: date, suffix: str
    ) -> None:
        """保存调试快照"""
        safe_name = f"mu_{route.from_city}_{route.to_city}_{flight_date.isoformat()}_{suffix}"
        html_path = self.debug_path / f"{safe_name}.html"
        png_path = self.debug_path / f"{safe_name}.png"

        try:
            html_path.write_text(await page.content(), encoding="utf-8")
        except Exception:
            pass

        try:
            await page.screenshot(path=str(png_path), full_page=True)
        except Exception:
            pass

    async def close(self) -> None:
        await self._save_cookies_from_context()
        if self.context:
            await self.context.close()
            self.context = None
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
```

- [ ] **运行测试验证通过**

```bash
pytest tests/test_mu_crawler.py -v
```

Expected: PASS

### Step 5.3: 提交

```bash
git add src/mu_crawler.py tests/test_mu_crawler.py
git commit -m "feat: add China Eastern Airlines (MU) crawler"
```

---

## Task 6: 新增深航爬虫

**Files:**
- Create: `src/zh_crawler.py`
- Test: `tests/test_zh_crawler.py`

### Step 6.1: 编写深航爬虫测试

- [ ] **创建测试文件**

```python
# tests/test_zh_crawler.py
import pytest
from src.zh_crawler import ZhCrawler, get_zh_city_code


def test_get_zh_city_code():
    """测试城市代码转换"""
    assert get_zh_city_code("深圳") == "SZX"
    assert get_zh_city_code("北京") == "PEK"
    assert get_zh_city_code("上海") == "SHA"


@pytest.mark.asyncio
async def test_zh_crawler_init():
    """测试深航爬虫初始化"""
    crawler = ZhCrawler(headless=True)
    assert crawler.source == "zh"
```

- [ ] **运行测试验证失败**

```bash
pytest tests/test_zh_crawler.py -v
```

Expected: FAIL

### Step 6.2: 实现深航爬虫

- [ ] **创建深航爬虫**（结构类似东航，针对深航网站调整）

```python
# src/zh_crawler.py
"""
Shenzhen Airlines (深圳航空) official-site crawler.
"""

# 实现结构同 mu_crawler.py，针对深航网站调整：
# - 城市代码映射
# - 搜索 URL 格式
# - 页面选择器
# - 航班号前缀 ZH

ZH_CITY_CODE_MAP = {
    "深圳": "SZX",
    "北京": "PEK",
    "上海": "SHA",
    # ... 其他城市
}

ZH_AIRLINE_NAME = "深圳航空"
ZH_HOMEPAGE_URL = "https://www.shenzhenair.com/"


def get_zh_city_code(city_name: str) -> str:
    return ZH_CITY_CODE_MAP.get(city_name, city_name)


class ZhCrawler(FlightCrawler):
    source = "zh"
    # 实现细节类似 MuCrawler
    ...
```

- [ ] **运行测试验证通过**

```bash
pytest tests/test_zh_crawler.py -v
```

### Step 6.3: 提交

```bash
git add src/zh_crawler.py tests/test_zh_crawler.py
git commit -m "feat: add Shenzhen Airlines (ZH) crawler"
```

---

## Task 7: 新增吉祥爬虫

**Files:**
- Create: `src/ho_crawler.py`
- Test: `tests/test_ho_crawler.py`

### Step 7.1: 编写吉祥爬虫测试

- [ ] **创建测试文件**

```python
# tests/test_ho_crawler.py
import pytest
from src.ho_crawler import HoCrawler, get_ho_city_code


def test_get_ho_city_code():
    """测试城市代码转换"""
    assert get_ho_city_code("上海") == "SHA"
    assert get_ho_city_code("南京") == "NKG"


@pytest.mark.asyncio
async def test_ho_crawler_init():
    """测试吉祥爬虫初始化"""
    crawler = HoCrawler(headless=True)
    assert crawler.source == "ho"
```

### Step 7.2: 实现吉祥爬虫

- [ ] **创建吉祥爬虫**（航班号前缀 HO）

```python
# src/ho_crawler.py
"""
Juneyao Air (吉祥航空) official-site crawler.
"""

HO_AIRLINE_NAME = "吉祥航空"
HO_HOMEPAGE_URL = "https://www.juneyaoair.com/"

# 实现结构同上
```

### Step 7.3: 提交

```bash
git add src/ho_crawler.py tests/test_ho_crawler.py
git commit -m "feat: add Juneyao Air (HO) crawler"
```

---

## Task 8: 更新配置和入口

**Files:**
- Modify: `src/config.py`
- Modify: `main.py`
- Modify: `config.example.yaml`

### Step 8.1: 更新配置验证

- [ ] **修改 config.py，添加新数据源**

```python
# 在 _validate_config 函数中更新有效数据源列表
valid_sources = {"csair", "ctrip", "feizhu", "spring", "mu", "zh", "ho"}
```

### Step 8.2: 更新主入口

- [ ] **修改 main.py，支持新爬虫**

```python
# 在 FlightMonitor.init() 中添加新爬虫的初始化
from src.mu_crawler import MuCrawler
from src.zh_crawler import ZhCrawler
from src.ho_crawler import HoCrawler

# 在初始化爬虫的逻辑中添加
elif self.config.monitor.default_source == "mu":
    self.crawler = MuCrawler(headless=self.config.monitor.headless)
elif self.config.monitor.default_source == "zh":
    self.crawler = ZhCrawler(headless=self.config.monitor.headless)
elif self.config.monitor.default_source == "ho":
    self.crawler = HoCrawler(headless=self.config.monitor.headless)
```

### Step 8.3: 更新配置示例

- [ ] **更新 config.example.yaml**

```yaml
monitor:
  default_source: "spring"  # 数据源: "spring", "csair", "mu", "zh", "ho"
  check_interval: 30
  headless: true
```

### Step 8.4: 提交

```bash
git add src/config.py main.py config.example.yaml
git commit -m "feat: add support for new airline crawlers in config"
```

---

## Task 9: 集成测试

### Step 9.1: 运行完整测试套件

- [ ] **运行所有测试**

```bash
pytest tests/ -v
```

### Step 9.2: 修复任何失败的测试

- [ ] **修复测试失败**

根据测试输出修复代码问题。

### Step 9.3: 最终提交

```bash
git add .
git commit -m "test: verify all crawlers pass integration tests"
```

---

## 验收清单

- [ ] Stealth 模块可用，测试通过
- [ ] Cookie 管理器可用，测试通过
- [ ] BaseCrawler 增强完成
- [ ] 南航爬虫集成新功能
- [ ] 东航爬虫可用
- [ ] 深航爬虫可用
- [ ] 吉祥爬虫可用
- [ ] 配置和入口更新完成
- [ ] 所有测试通过
