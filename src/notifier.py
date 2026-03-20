"""Notification module supporting email, webhook, and Bark."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List

import aiohttp

from src.config import NotificationsConfig, get_airport_name
from src.exceptions import NotifierError

logger = logging.getLogger(__name__)


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
        for flight in flights:
            await self._send_single_alert(flight, flight_date, threshold)

    async def _send_single_alert(
        self,
        flight: Dict[str, Any],
        flight_date,
        threshold: int,
    ) -> None:
        alert_id = (
            f"{flight['route_from']}-{flight['route_to']}-"
            f"{flight_date.isoformat()}-{flight['flight_no']}-{flight['source']}"
        )
        if alert_id in self._history:
            return
        self._history.add(alert_id)

        departure_airport = flight.get("departure_airport", "")
        arrival_airport = flight.get("arrival_airport", "")
        departure_name = get_airport_name(departure_airport) if departure_airport else ""
        arrival_name = get_airport_name(arrival_airport) if arrival_airport else ""

        route_from = flight["route_from"]
        route_to = flight["route_to"]
        if departure_name:
            route_from += f" (departure airport: {departure_name})"
        if arrival_name:
            route_to += f" (arrival airport: {arrival_name})"
        route_info = f"{route_from} -> {route_to}"

        source = flight.get("source", "unknown")
        source_label = f"[{source}]"
        title = f"Low price flight alert: {route_info} {source_label}"

        body_lines = [
            f"{route_info} ({flight_date.strftime('%Y-%m-%d')})",
            f"Flight: {flight['flight_no']} ({flight['airline']})",
            f"Price: RMB {flight['price']}",
            f"Threshold: RMB {threshold}",
            f"Source: {source}",
        ]
        email_body = "\n".join(body_lines)
        webhook_content = "\n".join([title, *body_lines])
        bark_content = "\n".join(
            [
                f"{flight['route_from']} -> {flight['route_to']}",
                f"Flight: {flight['flight_no']}",
                f"Price: RMB {flight['price']}",
            ]
        )

        tasks = []
        if self.config.email.enabled:
            tasks.append(self._send_email(title, email_body))
        if self.config.webhook.enabled:
            tasks.append(self._send_webhook(title, webhook_content))
        if self.config.bark.enabled:
            tasks.append(self._send_bark(title, bark_content))

        if tasks:
            import asyncio

            await asyncio.gather(*tasks, return_exceptions=True)

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
            raise NotifierError(f"Email alert failed: {exc}") from exc

    async def _send_webhook(self, title: str, content: str) -> None:
        cfg = self.config.webhook
        try:
            payload = {
                "msgtype": "text",
                "text": {"content": f"{title}\n\n{content}"},
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(cfg.url, json=payload) as resp:
                    if resp.status != 200:
                        raise NotifierError(f"Webhook returned status {resp.status}")

            logger.info("Webhook alert sent: %s", title)
        except Exception as exc:
            logger.error("Webhook alert failed: %s", exc)
            raise NotifierError(f"Webhook alert failed: {exc}") from exc

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
            raise NotifierError(f"Bark alert failed: {exc}") from exc
