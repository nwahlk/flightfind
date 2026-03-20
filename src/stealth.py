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
