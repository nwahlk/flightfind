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
