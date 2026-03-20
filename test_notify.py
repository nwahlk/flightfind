#!/usr/bin/env python3
"""测试飞书通知"""
import asyncio
from datetime import date

# 请替换为你的飞书Webhook URL
FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxx"

async def test():
    from src.notifier import Notifier
    from src.config import WebhookConfig, EmailConfig, BarkConfig, NotificationsConfig

    # 创建飞书通知配置
    webhook = WebhookConfig(enabled=True, url=FEISHU_WEBHOOK)
    email = EmailConfig(enabled=False)
    bark = BarkConfig(enabled=False)
    config = NotificationsConfig(email=email, webhook=webhook, bark=bark)

    notifier = Notifier(config)

    # 模拟低价航班
    test_flight = {
        "route_from": "深圳",
        "route_to": "上海",
        "flight_no": "9C7520",
        "airline": "春秋航空",
        "price": 510,
        "source": "ctrip",
        "departure_airport": "宝安国际机场T3",
        "arrival_airport": "虹桥国际机场T1",
        "metadata": {
            "departure_time": "13:50",
            "arrival_time": "15:55"
        }
    }

    print("发送测试通知到飞书...")
    await notifier.send_low_price_alert(
        [test_flight],
        flight_date=date(2026, 4, 3),
        threshold=800
    )
    print("发送完成！请检查飞书群消息")

if __name__ == "__main__":
    asyncio.run(test())
