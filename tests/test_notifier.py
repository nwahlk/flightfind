from datetime import date

import pytest

from src.config import BarkConfig, EmailConfig, NotificationsConfig, WebhookConfig
from src.exceptions import NotifierError
from src.notifier import Notifier


def _notifications_config() -> NotificationsConfig:
    return NotificationsConfig(
        email=EmailConfig(enabled=False),
        webhook=WebhookConfig(enabled=True, url="https://example.com/webhook"),
        bark=BarkConfig(enabled=False),
    )


def _flight():
    return {
        "route_from": "深圳",
        "route_to": "上海",
        "flight_no": "CA1883",
        "airline": "国航",
        "price": 400,
        "source": "flyai",
        "metadata": {"departure_time": "13:00"},
    }


@pytest.mark.asyncio
async def test_failed_notification_does_not_mark_history(monkeypatch):
    notifier = Notifier(_notifications_config())

    async def fail_send(*args, **kwargs):
        raise NotifierError("send failed")

    monkeypatch.setattr(notifier, "_send_webhook", fail_send)

    await notifier.send_low_price_alert([_flight()], date(2026, 5, 20), 800)

    assert notifier._history == set()


@pytest.mark.asyncio
async def test_successful_notification_marks_history(monkeypatch):
    notifier = Notifier(_notifications_config())

    async def success_send(*args, **kwargs):
        return None

    monkeypatch.setattr(notifier, "_send_webhook", success_send)

    await notifier.send_low_price_alert([_flight()], date(2026, 5, 20), 800)

    assert notifier._history == {
        "深圳-上海-2026-05-20-CA1883-flyai",
    }
