"""Cookie persistence for browser-backed sources."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class CookieManager:
    """Manage browser cookies on disk."""

    def __init__(self, cookie_dir: Path):
        self.cookie_dir = Path(cookie_dir)
        self.cookie_dir.mkdir(parents=True, exist_ok=True)

    def _get_cookie_path(self, site_name: str) -> Path:
        safe_name = site_name.replace("/", "_").replace("\\", "_")
        return self.cookie_dir / f"{safe_name}_cookies.json"

    async def save_cookies(self, site_name: str, cookies: List[Dict[str, Any]]) -> None:
        if not cookies:
            return
        cookie_path = self._get_cookie_path(site_name)
        try:
            cookie_path.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to save cookies for %s: %s", site_name, exc)

    async def load_cookies(self, site_name: str) -> List[Dict[str, Any]]:
        cookie_path = self._get_cookie_path(site_name)
        if not cookie_path.exists():
            return []
        try:
            return json.loads(cookie_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load cookies for %s: %s", site_name, exc)
            return []

    async def clear_cookies(self, site_name: str) -> None:
        cookie_path = self._get_cookie_path(site_name)
        if cookie_path.exists():
            try:
                cookie_path.unlink()
            except Exception as exc:
                logger.warning("Failed to clear cookies for %s: %s", site_name, exc)
