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

    async def send_low_price_alert(self, flights: List[Dict[str, Any]], flight_date, threshold: int) -> None:
        """
        发送低价提醒

        Args:
            flights: 低价航班列表
            flight_date: 航班日期
            threshold: 价格阈值
        """
        for flight in flights:
            await self._send_single_alert(flight, flight_date, threshold)

    async def _send_single_alert(self, flight: Dict[str, Any], flight_date, threshold: int) -> None:
        """
        发送单个航班提醒

        Args:
            flight: 航班信息
            flight_date: 航班日期
            threshold: 价格阈值
        """
        # 生成唯一标识避免重复通知
        alert_id = f"{flight['route_from']}-{flight['route_to']}-{flight_date.isoformat()}-{flight['flight_no']}-{flight['source']}"

        if alert_id in self._history:
            return

        self._history.add(alert_id)

        # 获取机场名称
        from src.config import get_airport_name
        departure_airport = flight.get('departure_airport', '')
        arrival_airport = flight.get('arrival_airport', '')
        departure_name = get_airport_name(departure_airport) if departure_airport else ''
        arrival_name = get_airport_name(arrival_airport) if arrival_airport else ''

        # 构建航线信息（包含机场）
        departure_part = f"出发：{departure_name}" if departure_name else ""
        arrival_part = f"到达：{arrival_name}" if arrival_name else ""

        route_info = f"{flight['route_from']}({departure_part}) → {flight['route_to']}({arrival_part})"

        # 构建消息 - 添加来源标签
        source_label = f"【{flight.get('source', '未知')}】"
        title = f"✈️ 低价机票: {route_info} {source_label}"

        # 邮件内容（包含机场信息）
        email_body = f"""
{route_info} ({flight_date.strftime('%Y-%m-%d')})
航班: {flight['flight_no']} ({flight['airline']})
价格: ¥{flight['price']}
{departure_part}
{arrival_part}
阈值: ¥{threshold}
来源: {flight.get('source', '未知')}
            """.strip()

        # Webhook 内容（包含机场信息）
        webhook_content = f"""{title}
{route_info} ({flight_date.strftime('%Y-%m-%d')})
航班: {flight['flight_no']} ({flight['airline']})
价格: ¥{flight['price']}
{departure_part}
{arrival_part}
阈值: ¥{threshold}
来源: {flight.get('source', '未知')}
            """.strip()

        # Bark 内容（简化，避免字符限制）
        bark_content = f"""{flight['route_from']} → {flight['route_to']}
航班: {flight['flight_no']}
价格: ¥{flight['price']}
            """.strip()

        # 发送通知
        tasks = []
        source = flight.get('source', '未知')

        if self.config.email.enabled:
            tasks.append(self._send_email(title, email_body, source))

        if self.config.webhook.enabled:
            tasks.append(self._send_webhook(title, webhook_content, source))

        if self.config.bark.enabled:
            tasks.append(self._send_bark(title, bark_content, source))

        if tasks:
            import asyncio
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_email(self, title: str, content: str, source: str = '未知') -> None:
        """发送邮件"""
        cfg = self.config.email

        try:
            msg = MIMEMultipart()
            msg['From'] = cfg.username
            msg['To'] = ', '.join(cfg.to)
            msg['Subject'] = title

            # 在邮件内容中添加来源标签
            content_with_source = f"【{source}】\n\n{content}"
            msg.attach(MIMEText(content_with_source, 'plain', 'utf-8'))

            with smtplib.SMTP_SSL(cfg.smtp_server, cfg.smtp_port) as server:
                server.login(cfg.username, cfg.password)
                server.send_message(msg)

            logger.info(f"邮件已发送: {title}")

        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            raise NotifierError(f"邮件发送失败: {e}")

    async def _send_webhook(self, title: str, content: str, source: str = '未知') -> None:
        """发送Webhook"""
        cfg = self.config.webhook

        try:
            # 在消息中添加来源标签
            message = f"{title}\n\n【{source}】\n\n{content}"
            payload = {
                "msgtype": "text",
                "text": {"content": message}
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(cfg.url, json=payload) as resp:
                    if resp.status != 200:
                        raise NotifierError(f"Webhook返回错误: {resp.status}")

            logger.info(f"Webhook已发送: {title}")

        except Exception as e:
            logger.error(f"Webhook发送失败: {e}")
            raise NotifierError(f"Webhook发送失败: {e}")

    async def _send_bark(self, title: str, content: str, source: str = '未知') -> None:
        """发送Bark推送"""
        cfg = self.config.bark

        try:
            import urllib.parse
            # 在消息中添加来源标签
            content_with_source = f"【{source}】\n\n{content}"
            encoded_title = urllib.parse.quote(title)
            encoded_content = urllib.parse.quote(content_with_source)

            url = f"{cfg.server}/{cfg.device_key}/{encoded_title}/{encoded_content}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise NotifierError(f"Bark返回错误: {resp.status}")

            logger.info(f"Bark已发送: {title}")

        except Exception as e:
            logger.error(f"Bark发送失败: {e}")
            raise NotifierError(f"Bark发送失败: {e}")
