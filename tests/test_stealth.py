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
