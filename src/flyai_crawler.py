"""FlyAI (飞猪) 数据源 — 通过 CLI 调用飞猪 API，无需 Playwright 浏览器。"""

import asyncio
import json
import logging
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.base_crawler import FlightCrawler
from src.config import FlyAIConfig, Route
from src.exceptions import CrawlerError, ParseError
from src.flight_record import normalize_flight_record

logger = logging.getLogger(__name__)

# CLI 超时时间（秒）
_CLI_TIMEOUT = 60


def _resolve_flyai_cmd() -> str:
    """定位 flyai 可执行文件路径，兼容 Windows .cmd 包装脚本。"""
    path = shutil.which("flyai")
    if path:
        return path
    appdata = os.environ.get("APPDATA")
    candidates = []
    if appdata:
        candidates.append(Path(appdata) / "npm" / "flyai.cmd")
    candidates.append(Path.home() / "AppData" / "Roaming" / "npm" / "flyai.cmd")
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError


def _has_flyai_cli_profile() -> bool:
    """Return whether flyai CLI has a saved API key profile."""
    config_path = Path.home() / ".flyai" / "config.json"
    if not config_path.exists():
        return False
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("FLYAI_API_KEY") or data.get("defaultAuthorization"))


class FlyAIBaseCrawler(FlightCrawler):
    """Shared FlyAI CLI lifecycle helpers."""

    source = "flyai"

    def __init__(self, flyai_config: Optional[FlyAIConfig] = None) -> None:
        super().__init__(headless=False)
        self.flyai_config = flyai_config or FlyAIConfig()

    def _build_env(self) -> Dict[str, str]:
        """Build CLI env with optional official FlyAI credentials."""
        env = os.environ.copy()
        if self.flyai_config.api_key:
            env["FLYAI_API_KEY"] = self.flyai_config.api_key
        if self.flyai_config.sign_secret:
            env["FLYAI_SIGN_SECRET"] = self.flyai_config.sign_secret
        return env

    async def init(self) -> None:
        """验证 flyai CLI 是否可用。"""
        try:
            flyai_cmd = _resolve_flyai_cmd()
        except FileNotFoundError:
            raise CrawlerError(
                "FlyAI CLI 未安装，请运行: npm install -g @fly-ai/flyai-cli"
            )
        try:
            proc = await asyncio.create_subprocess_exec(
                flyai_cmd, "--help",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._build_env(),
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
        except asyncio.TimeoutError:
            raise CrawlerError("FlyAI CLI 启动超时")
        self._flyai_cmd = flyai_cmd
        if self.flyai_config.enabled:
            logger.info("[flyai] 使用配置文件中的正式凭证")
        elif os.environ.get("FLYAI_API_KEY") or os.environ.get("DEBUG_FLYAI_API_KEY"):
            logger.info("[flyai] 使用环境变量中的正式凭证")
        elif _has_flyai_cli_profile():
            logger.info("[flyai] 使用 flyai CLI 配置文件中的正式凭证")
        else:
            logger.warning(
                "[flyai] 未检测到 FLYAI_API_KEY，可能使用 CLI 默认体验模式"
            )
        logger.info("[flyai] 初始化完成（CLI 模式，无需浏览器）")

    async def close(self) -> None:
        """无资源需要释放。"""
        logger.info("[%s] 已关闭", self.source)


class FlyAICrawler(FlyAIBaseCrawler):
    """通过 flyai-cli 调用飞猪 API 搜索航班，不需要浏览器。"""

    source = "flyai"

    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        """搜索航班，遍历配置的所有日期。"""
        results: List[Dict[str, Any]] = []
        dates = sorted(route.dates.resolved_dates())

        for i, flight_date in enumerate(dates):
            if i:
                await asyncio.sleep(2)
            logger.info(
                "[flyai] 搜索 %s -> %s (%s)",
                route.from_city, route.to_city, flight_date,
            )
            try:
                items = await self._search_single_date(
                    route.from_city, route.to_city, flight_date,
                )
                results.extend(items)
            except CrawlerError:
                logger.warning(
                    "[flyai] %s -> %s (%s) 搜索失败，跳过",
                    route.from_city, route.to_city, flight_date,
                )
        return results

    async def _search_single_date(
        self, from_city: str, to_city: str, flight_date: date,
    ) -> List[Dict[str, Any]]:
        """调用 flyai search-flight CLI 并解析结果。"""
        try:
            flyai_cmd = getattr(self, "_flyai_cmd", None) or _resolve_flyai_cmd()
        except FileNotFoundError:
            raise CrawlerError(
                "FlyAI CLI 未安装，请运行: npm install -g @fly-ai/flyai-cli"
            )
        try:
            proc = await asyncio.create_subprocess_exec(
                flyai_cmd, "search-flight",
                "--origin", from_city,
                "--destination", to_city,
                "--dep-date", flight_date.isoformat(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._build_env(),
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=_CLI_TIMEOUT,
            )
        except FileNotFoundError:
            raise CrawlerError(
                "FlyAI CLI 未安装，请运行: npm install -g @fly-ai/flyai-cli"
            )
        except asyncio.TimeoutError:
            raise CrawlerError("FlyAI CLI 请求超时")

        try:
            data = json.loads(stdout_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
            if proc.returncode != 0:
                raise CrawlerError(f"FlyAI CLI 错误: {stderr_text or 'exit code ' + str(proc.returncode)}")
            raise ParseError(f"FlyAI CLI 返回无效 JSON: {exc}") from exc

        if proc.returncode != 0:
            logger.warning("FlyAI CLI exited with %s after returning JSON", proc.returncode)

        if data.get("status") != 0:
            raise CrawlerError(f"FlyAI API 错误: {data.get('message', '未知错误')}")

        item_list = data.get("data", {}).get("itemList") or []
        results: List[Dict[str, Any]] = []
        for item in item_list:
            record = self._parse_flight_item(item, from_city, to_city, flight_date)
            if record:
                results.append(record)

        logger.info("[flyai] 找到 %d 条航班", len(results))
        return results

    def _parse_flight_item(
        self, item: dict, from_city: str, to_city: str, flight_date: date,
    ) -> Optional[Dict[str, Any]]:
        """将单条 FlyAI 航班数据转为标准化记录。"""
        try:
            price = self._parse_price(item.get("adultPrice") or item.get("ticketPrice") or "")

            journeys = item.get("journeys", [])
            if not journeys:
                return None

            segments = journeys[0].get("segments", [])
            if not segments:
                return None

            seg = segments[0]
            metadata = {
                "departure_time": seg.get("depDateTime", ""),
                "arrival_time": seg.get("arrDateTime", ""),
                "duration": seg.get("duration", ""),
                "seat_class": seg.get("seatClassName", ""),
                "journey_type": journeys[0].get("journeyType", ""),
                "booking_url": item.get("jumpUrl", ""),
            }

            return normalize_flight_record(
                route_from=from_city,
                route_to=to_city,
                flight_date=flight_date,
                flight_no=seg.get("marketingTransportNo", ""),
                airline=seg.get("marketingTransportName", ""),
                price=price,
                source=self.source,
                departure_airport=seg.get("depStationName", ""),
                arrival_airport=seg.get("arrStationName", ""),
                metadata=metadata,
            )
        except Exception:
            logger.warning("[flyai] 解析航班数据失败", exc_info=True)
            return None

    @staticmethod
    def _parse_price(price_str: str) -> int:
        """解析价格字符串，如 '¥400.0' → 400。"""
        if not price_str:
            return 0
        if "x" in str(price_str).lower():
            return 0
        cleaned = re.sub(r"[^\d.]", "", price_str)
        try:
            return int(float(cleaned))
        except (ValueError, OverflowError):
            return 0

class FlyAITrainCrawler(FlyAIBaseCrawler):
    """通过 flyai-cli 调用高铁/火车 API 搜索车次。"""

    source = "flyai_train"

    async def search_flights(self, route: Route) -> List[Dict[str, Any]]:
        """搜索高铁/火车，返回与主流程兼容的标准记录。"""
        results: List[Dict[str, Any]] = []
        dates = sorted(route.dates.resolved_dates())

        for i, train_date in enumerate(dates):
            if i:
                await asyncio.sleep(2)
            logger.info(
                "[flyai_train] 搜索 %s -> %s (%s)",
                route.from_city, route.to_city, train_date,
            )
            try:
                items = await self._search_single_date(
                    route.from_city, route.to_city, train_date,
                )
                results.extend(items)
            except CrawlerError:
                logger.warning(
                    "[flyai_train] %s -> %s (%s) 搜索失败，跳过",
                    route.from_city, route.to_city, train_date,
                )
        return results

    async def _search_single_date(
        self, from_city: str, to_city: str, train_date: date,
    ) -> List[Dict[str, Any]]:
        """调用 flyai search-train CLI 并解析结果。"""
        try:
            flyai_cmd = getattr(self, "_flyai_cmd", None) or _resolve_flyai_cmd()
        except FileNotFoundError:
            raise CrawlerError(
                "FlyAI CLI 未安装，请运行: npm install -g @fly-ai/flyai-cli"
            )
        try:
            proc = await asyncio.create_subprocess_exec(
                flyai_cmd, "search-train",
                "--origin", from_city,
                "--destination", to_city,
                "--dep-date", train_date.isoformat(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._build_env(),
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=_CLI_TIMEOUT,
            )
        except FileNotFoundError:
            raise CrawlerError(
                "FlyAI CLI 未安装，请运行: npm install -g @fly-ai/flyai-cli"
            )
        except asyncio.TimeoutError:
            raise CrawlerError("FlyAI CLI 高铁请求超时")

        try:
            data = json.loads(stdout_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
            if proc.returncode != 0:
                raise CrawlerError(f"FlyAI CLI 高铁错误: {stderr_text or 'exit code ' + str(proc.returncode)}")
            raise ParseError(f"FlyAI CLI 高铁返回无效 JSON: {exc}") from exc

        if proc.returncode != 0:
            logger.warning("FlyAI train CLI exited with %s after returning JSON", proc.returncode)

        if data.get("status") != 0:
            raise CrawlerError(f"FlyAI 高铁 API 错误: {data.get('message', '未知错误')}")

        item_list = data.get("data", {}).get("itemList") or data.get("data", {}).get("trainList") or []
        results: List[Dict[str, Any]] = []
        for item in item_list:
            record = self._parse_train_item(item, from_city, to_city, train_date)
            if record:
                results.append(record)

        logger.info("[flyai_train] 找到 %d 条车次", len(results))
        return results

    def _parse_train_item(
        self, item: dict, from_city: str, to_city: str, train_date: date,
    ) -> Optional[Dict[str, Any]]:
        """将单条 FlyAI 高铁/火车数据转为主流程兼容记录。"""
        try:
            price_text = self._first_present(
                item,
                "adultPrice", "ticketPrice", "price", "minPrice",
                "secondClassPrice", "secondSeatPrice",
            )
            price = self._parse_price(price_text)
            if price <= 0:
                # FlyAI trial mode may mask train prices as "5xx"; keep the
                # result queryable while making it ineligible for low-price alerts.
                price = 999999

            segment = self._first_segment(item)
            train_no = self._first_present(
                segment, "trainNo", "trainCode", "trainNumber",
                "transportNo", "marketingTransportNo",
            ) or self._first_present(
                item, "trainNo", "trainCode", "trainNumber", "transportNo",
            )
            dep_station = self._first_present(
                segment, "depStationName", "fromStationName", "startStationName",
                "departureStationName",
            ) or self._first_present(
                item, "depStationName", "fromStationName", "startStationName",
            )
            arr_station = self._first_present(
                segment, "arrStationName", "toStationName", "endStationName",
                "arrivalStationName",
            ) or self._first_present(
                item, "arrStationName", "toStationName", "endStationName",
            )
            dep_time = self._first_present(
                segment, "depDateTime", "departureTime", "startTime", "depTime",
            ) or self._first_present(item, "depDateTime", "departureTime", "startTime")
            arr_time = self._first_present(
                segment, "arrDateTime", "arrivalTime", "endTime", "arrTime",
            ) or self._first_present(item, "arrDateTime", "arrivalTime", "endTime")
            train_type = self._first_present(
                segment, "trainType", "seatClassName", "transportName",
                "marketingTransportName",
            ) or self._first_present(item, "trainType", "seatClassName", "transportName")

            return normalize_flight_record(
                route_from=from_city,
                route_to=to_city,
                flight_date=train_date,
                flight_no=train_no or "Unknown",
                airline=train_type or "Train",
                price=price,
                source=self.source,
                departure_airport=dep_station,
                arrival_airport=arr_station,
                metadata={
                    "transport_type": "train",
                    "departure_time": dep_time,
                    "arrival_time": arr_time,
                    "duration": self._first_present(item, "duration", "totalDuration"),
                    "price_text": price_text,
                    "seat_class": self._first_present(segment, "seatClassName")
                    or self._first_present(item, "seatClassName"),
                    "booking_url": self._first_present(item, "jumpUrl", "bookingUrl"),
                },
            )
        except Exception:
            logger.warning("[flyai_train] 解析高铁数据失败", exc_info=True)
            return None

    @staticmethod
    def _first_present(source: dict, *keys: str) -> str:
        for key in keys:
            value = source.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    @staticmethod
    def _first_segment(item: dict) -> dict:
        journeys = item.get("journeys") or []
        if journeys and isinstance(journeys[0], dict):
            segments = journeys[0].get("segments") or []
            if segments and isinstance(segments[0], dict):
                return segments[0]
        return item

    @staticmethod
    def _parse_price(price_str: str) -> int:
        return FlyAICrawler._parse_price(price_str)
