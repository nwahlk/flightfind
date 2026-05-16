"""Browser fingerprint helpers for browser-backed sources."""

import random
from typing import Dict


DESKTOP_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_random_desktop_ua() -> str:
    return random.choice(DESKTOP_USER_AGENTS)


def get_random_viewport(mobile: bool = False) -> Dict[str, int]:
    if mobile:
        return random.choice(
            [
                {"width": 375, "height": 812},
                {"width": 390, "height": 844},
                {"width": 412, "height": 915},
            ]
        )
    return random.choice(
        [
            {"width": 1920, "height": 1080},
            {"width": 1440, "height": 900},
            {"width": 1536, "height": 864},
        ]
    )


def get_stealth_init_script() -> str:
    return """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });
    Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
    window.chrome = window.chrome || { runtime: {} };
    """
