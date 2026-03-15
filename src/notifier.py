"""
通知模块 - 支持邮件、Webhook、Bark
"""

import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Any
import aiohttp
from src.config import NotificationsConfig, EmailConfig, WebhookConfig, BarkConfig
from src.exceptions import NotifierError
import logging

logger = logging.getLogger(__name__)


class Notifier:
    """通知管理器"""

    def __init__(self, config: NotificationsConfig):
        self.config = config
        self._history = set()  # 避免重复通知

    async def send_low_price_alert(self, flights: List[Dict[str, Any]]) -> None:
        """
        发送低价提醒

        Args:
            flights: 低价航班列表
        """
        for flight in flights:
            # 生成唯一标识避免重复通知
            alert_id = f"{flight['route_from']}-{flight['route_to']}-{flight['date']}-{flight['flight_no']}"

            if alert_id in self._history:
                continue

            self._history.add(alert_id)

            # 构建消息
            title = f"✈️ 低价机票: {flight['route_from']} → {flight['route_to']}"
            content = f"""
航班: {flight['flight_no']}
航空: {flight['airline']}
日期: {flight['date']}
价格: ¥{flight['price']}
            """.strip()

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

    async def _send_email(self, title: str, content: str) -> None:
        """发送邮件"""
        cfg = self.config.email

        try:
            msg = MIMEMultipart()
            msg['From'] = cfg.username
            msg['To'] = ', '.join(cfg.to)
            msg['Subject'] = title

            msg.attach(MIMEText(content, 'plain', 'utf-8'))

            with smtplib.SMTP_SSL(cfg.smtp_server, cfg.smtp_port) as server:
                server.login(cfg.username, cfg.password)
                server.send_message(msg)

            logger.info(f"邮件已发送: {title}")

        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            raise NotifierError(f"邮件发送失败: {e}")

    async def _send_webhook(self, title: str, content: str) -> None:
        """发送Webhook"""
        cfg = self.config.webhook

        try:
            payload = {
                "msgtype": "text",
                "text": {"content": f"{title}\n\n{content}"}
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(cfg.url, json=payload) as resp:
                    if resp.status != 200:
                        raise NotifierError(f"Webhook返回错误: {resp.status}")

            logger.info(f"Webhook已发送: {title}")

        except Exception as e:
            logger.error(f"Webhook发送失败: {e}")
            raise NotifierError(f"Webhook发送失败: {e}")

    async def _send_bark(self, title: str, content: str) -> None:
        """发送Bark推送"""
        cfg = self.config.bark

        try:
            import urllib.parse
            encoded_title = urllib.parse.quote(title)
            encoded_content = urllib.parse.quote(content)

            url = f"{cfg.server}/{cfg.device_key}/{encoded_title}/{encoded_content}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise NotifierError(f"Bark返回错误: {resp.status}")

            logger.info(f"Bark已发送: {title}")

        except Exception as e:
            logger.error(f"Bark发送失败: {e}")
            raise NotifierError(f"Bark发送失败: {e}")
