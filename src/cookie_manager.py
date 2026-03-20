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
