"""Notification module supporting email, webhook, and Bark."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import aiohttp

from src.config import NotificationsConfig
from src.exceptions import NotifierError

logger = logging.getLogger(__name__)

# 最多显示的航班数量
MAX_FLIGHTS_IN_ALERT = 10


class Notifier:
    """Send low-price alerts through configured channels."""

    def __init__(self, config: NotificationsConfig):
        self.config = config
        self._history = set()

    async def send_low_price_alert(
        self,
        flights: List[Dict[str, Any]],
        flight_date,
        threshold: int,
    ) -> None:
        """批量发送低价航班提醒（合并为一条消息）"""
        if not flights:
            return

        # 过滤已发送过的航班
        new_flights = []
        for flight in flights:
            alert_id = (
                f"{flight['route_from']}-{flight['route_to']}-"
                f"{flight_date.isoformat()}-{flight['flight_no']}-{flight['source']}"
            )
            if alert_id not in self._history:
                self._history.add(alert_id)
                new_flights.append(flight)

        if not new_flights:
            return

        # 按价格排序
        sorted_flights = sorted(new_flights, key=lambda x: x["price"])

        # 按时间段过滤
        time_start = getattr(self.config, 'time_filter_start', None)
        time_end = getattr(self.config, 'time_filter_end', None)
        if time_start and time_end:
            filtered_flights = self._filter_by_time(sorted_flights, time_start, time_end)
            if filtered_flights:
                sorted_flights = filtered_flights
            # 如果过滤后为空，仍然发送原始列表（避免漏掉重要信息）

        # 取前N个
        display_flights = sorted_flights[:MAX_FLIGHTS_IN_ALERT]

        # 构建合并消息
        title, content = self._build_batch_message(display_flights, flight_date, threshold, len(sorted_flights))

        # 发送通知
        tasks = []
        if self.config.email.enabled:
            tasks.append(self._send_email(title, content))
        if self.config.webhook.enabled:
            tasks.append(self._send_webhook(title, content))
        if self.config.bark.enabled:
            tasks.append(self._send_bark(title, content))

        if tasks:
            import asyncio
            await asyncio.gather(*tasks, return_exceptions=True)

    def _filter_by_time(
        self,
        flights: List[Dict[str, Any]],
        time_start: str,
        time_end: str,
    ) -> List[Dict[str, Any]]:
        """按起飞时间段过滤航班"""
        try:
            start_hour = int(time_start.split(':')[0])
            end_hour = int(time_end.split(':')[0])

            filtered = []
            for flight in flights:
                dep_time = flight.get("metadata", {}).get("departure_time", "")
                if dep_time:
                    try:
                        hour = int(dep_time.split(':')[0])
                        if start_hour <= hour < end_hour:
                            filtered.append(flight)
                    except (ValueError, IndexError):
                        continue

            return filtered
        except Exception as e:
            logger.warning("Time filter error: %s", e)
            return flights

    def _build_batch_message(
        self,
        flights: List[Dict[str, Any]],
        flight_date,
        threshold: int,
        total_count: int = None,
    ) -> tuple:
        """构建批量消息"""
        first = flights[0]
        route = f"{first['route_from']} → {first['route_to']}"
        min_price = flights[0]["price"]
        date_str = flight_date.strftime("%Y-%m-%d")

        # 标题
        title = f"✈️ {route} {date_str} 最低¥{min_price}"

        # 时间段过滤信息
        time_start = getattr(self.config, 'time_filter_start', None)
        time_end = getattr(self.config, 'time_filter_end', None)
        time_filter_str = ""
        if time_start and time_end:
            time_filter_str = f" ({time_start}-{time_end})"

        # 内容 - 紧凑格式
        count_str = f"{len(flights)}" + (f"/{total_count}" if total_count and total_count > len(flights) else "")
        lines = [
            f"**航线**: {route}",
            f"**日期**: {date_str}{time_filter_str}",
            f"**阈值**: ¥{threshold}",
            f"**低价航班 {count_str} 个**:",
            "---",
        ]

        for f in flights:
            dep_airport = f.get("departure_airport", "")
            arr_airport = f.get("arrival_airport", "")
            dep_time = f.get("metadata", {}).get("departure_time", "")
            arr_time = f.get("metadata", {}).get("arrival_time", "")

            # 单行格式: 航班号 航空公司 价格 时间 机场
            flight_line = f"`{f['flight_no']}` {f['airline']} **¥{f['price']}**"
            if dep_time:
                flight_line += f" {dep_time}"
            if dep_airport and arr_airport:
                # 简化机场名
                dep_short = dep_airport.replace("国际机场", "").replace("机场", "")
                arr_short = arr_airport.replace("国际机场", "").replace("机场", "")
                flight_line += f" {dep_short}→{arr_short}"

            lines.append(flight_line)

        if total_count and total_count > len(flights):
            lines.append("---")
            lines.append(f"_仅显示前{len(flights)}个最低价航班_")

        content = "\n".join(lines)
        return title, content

    async def _send_email(self, title: str, content: str) -> None:
        cfg = self.config.email
        try:
            msg = MIMEMultipart()
            msg["From"] = cfg.username
            msg["To"] = ", ".join(cfg.to)
            msg["Subject"] = title
            msg.attach(MIMEText(content, "plain", "utf-8"))

            with smtplib.SMTP_SSL(cfg.smtp_server, cfg.smtp_port) as server:
                server.login(cfg.username, cfg.password)
                server.send_message(msg)

            logger.info("Email alert sent: %s", title)
        except Exception as exc:
            logger.error("Email alert failed: %s", exc)

    async def _send_webhook(self, title: str, content: str) -> None:
        cfg = self.config.webhook
        try:
            # 判断是飞书还是企业微信/钉钉
            if "feishu.cn" in cfg.url or "larksuite.com" in cfg.url:
                # 飞书格式 - 交互式卡片
                payload = {
                    "msg_type": "interactive",
                    "card": {
                        "header": {
                            "title": {"tag": "plain_text", "content": title},
                            "template": "green"
                        },
                        "elements": [
                            {"tag": "markdown", "content": content}
                        ]
                    }
                }
            else:
                # 企业微信/钉钉格式
                payload = {
                    "msgtype": "text",
                    "text": {"content": f"{title}\n\n{content}"},
                }

            async with aiohttp.ClientSession() as session:
                async with session.post(cfg.url, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise NotifierError(f"Webhook returned status {resp.status}: {text}")

            logger.info("Webhook alert sent: %s", title)
        except Exception as exc:
            logger.error("Webhook alert failed: %s", exc)

    async def _send_bark(self, title: str, content: str) -> None:
        cfg = self.config.bark
        try:
            import urllib.parse

            encoded_title = urllib.parse.quote(title)
            encoded_content = urllib.parse.quote(content)
            url = f"{cfg.server}/{cfg.device_key}/{encoded_title}/{encoded_content}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise NotifierError(f"Bark returned status {resp.status}")

            logger.info("Bark alert sent: %s", title)
        except Exception as exc:
            logger.error("Bark alert failed: %s", exc)
