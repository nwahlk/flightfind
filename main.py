#!/usr/bin/env python3
"""
FlightFind - 航班价格监控工具
支持数据源: ctrip(携程), spring(春秋航空)
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from src.config import load_config
from src.ctrip_crawler import CtripCrawler
from src.database import Database
from src.exporter import FlightExporter
from src.notifier import Notifier
from src.spring_crawler import SpringCrawler
from src.utils import setup_logging

logger = logging.getLogger(__name__)


def create_crawler(source: str, headless: bool):
    """创建爬虫实例"""
    if source == "spring":
        return SpringCrawler(headless=headless)
    else:  # 默认使用 ctrip
        return CtripCrawler(headless=headless)


class FlightMonitor:
    """航班监控主程序"""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = None
        self.db = None
        self.crawlers: Dict[str, any] = {}
        self.notifier = None
        self.exporter = None

    async def init(self) -> None:
        self.config = load_config(self.config_path)

        setup_logging(log_file=Path("logs/monitor.log"), level=logging.INFO)
        logger.info("=" * 50)
        logger.info("FlightFind 启动")
        logger.info("=" * 50)

        self.db = Database(Path("data/flights.db"))
        await self.db.init()

        # 初始化所有数据源的爬虫
        for source in self.config.monitor.sources:
            logger.info("初始化爬虫: %s", source)
            crawler = create_crawler(source, self.config.monitor.headless)
            await crawler.init()
            self.crawlers[source] = crawler

        self.notifier = Notifier(self.config.notifications)
        self.exporter = FlightExporter(Path("exports"))

        logger.info("数据源: %s", ", ".join(self.config.monitor.sources))
        logger.info("监控航线: %d 条", len(self.config.routes))
        for route in self.config.routes:
            logger.info(
                "  - %s -> %s, 阈值=%d, 日期数=%d",
                route.from_city,
                route.to_city,
                route.low_price_threshold,
                len(route.dates.absolute_dates),
            )

    async def run_check(self) -> None:
        """执行一次监控检查"""
        if not self.crawlers:
            logger.error("爬虫未初始化")
            return

        all_export_rows = []

        for source_name, crawler in self.crawlers.items():
            logger.info("=" * 30)
            logger.info("使用数据源: %s", source_name)
            logger.info("=" * 30)

            export_rows = await self._run_crawler(source_name, crawler)
            all_export_rows.extend(export_rows)

        # 导出汇总报告
        if all_export_rows and self.exporter:
            export_path = self.exporter.export_run_summary(all_export_rows, format="xlsx")
            logger.info("报告已导出: %s", export_path)

    async def _run_crawler(self, source_name: str, crawler) -> List[dict]:
        """运行单个爬虫"""
        export_rows = []

        for route in self.config.routes:
            route_start = datetime.now()

            try:
                logger.info("查询航线 %s -> %s", route.from_city, route.to_city)
                flights = await crawler.search_flights(route)
            except Exception as exc:
                logger.error("查询失败: %s -> %s - %s", route.from_city, route.to_city, exc)
                for target_date in route.dates.absolute_dates:
                    export_rows.append(
                        self._build_export_row(
                            route_from=route.from_city,
                            route_to=route.to_city,
                            target_date=target_date,
                            threshold=route.low_price_threshold,
                            source=source_name,
                            status="failed",
                            message=str(exc),
                        )
                    )
                continue

            # 按日期分组
            flights_by_date = {d: [] for d in route.dates.absolute_dates}
            for flight in flights:
                flight_date = flight.get("flight_date")
                if flight_date in flights_by_date:
                    flights_by_date[flight_date].append(flight)

            for target_date in route.dates.absolute_dates:
                date_flights = flights_by_date.get(target_date, [])

                if not date_flights:
                    logger.warning("未找到航班: %s -> %s (%s)", route.from_city, route.to_city, target_date)
                    export_rows.append(
                        self._build_export_row(
                            route_from=route.from_city,
                            route_to=route.to_city,
                            target_date=target_date,
                            threshold=route.low_price_threshold,
                            source=source_name,
                            status="warning",
                            message="未找到航班",
                        )
                    )
                    continue

                # 按价格排序
                sorted_flights = sorted(date_flights, key=lambda f: f["price"])

                # 找出低价航班
                low_price_flights = [f for f in sorted_flights if f["price"] <= route.low_price_threshold]

                # 记录到导出
                display_flights = low_price_flights[:] or sorted_flights[:1]
                for flight in display_flights:
                    message = (
                        "低于阈值"
                        if flight["price"] <= route.low_price_threshold
                        else f"高于阈值，最低价: {sorted_flights[0]['price']}"
                    )
                    export_rows.append(
                        self._build_export_row(
                            route_from=flight["route_from"],
                            route_to=flight["route_to"],
                            target_date=target_date,
                            threshold=route.low_price_threshold,
                            source=flight["source"],
                            status="success",
                            message=message,
                            flight=flight,
                        )
                    )

                # 保存价格历史
                for flight in sorted_flights:
                    await self.db.save_price_history(
                        route_from=flight["route_from"],
                        route_to=flight["route_to"],
                        flight_date=target_date,
                        flight_no=flight["flight_no"],
                        airline=flight["airline"],
                        price=flight["price"],
                        source=flight["source"],
                    )

                # 发送低价提醒
                if low_price_flights:
                    await self.notifier.send_low_price_alert(
                        low_price_flights,
                        flight_date=target_date,
                        threshold=route.low_price_threshold,
                    )

                    channels = self._get_enabled_channels()
                    for flight in low_price_flights:
                        await self.db.save_alert(
                            route_from=flight["route_from"],
                            route_to=flight["route_to"],
                            flight_date=target_date,
                            flight_no=flight["flight_no"],
                            airline=flight["airline"],
                            price=flight["price"],
                            threshold=route.low_price_threshold,
                            channels=channels,
                            source=flight["source"],
                        )

                    logger.info("发现 %d 个低价航班", len(low_price_flights))
                else:
                    logger.info("未发现低于阈值的航班，最低价: %d", sorted_flights[0]["price"])

                # 记录执行日志
                execution_time = int((datetime.now() - route_start).total_seconds() * 1000)
                await self.db.log_execution(
                    job_id=f"{source_name}_{route.from_city}_{route.to_city}_{target_date.isoformat()}",
                    route_from=route.from_city,
                    route_to=route.to_city,
                    flight_date=target_date.isoformat(),
                    status="success",
                    message=f"找到 {len(sorted_flights)} 个航班",
                    execution_time_ms=execution_time,
                    source=source_name,
                )

        return export_rows

    def _get_enabled_channels(self) -> List[str]:
        channels = []
        if self.config.notifications.email.enabled:
            channels.append("email")
        if self.config.notifications.webhook.enabled:
            channels.append("webhook")
        if self.config.notifications.bark.enabled:
            channels.append("bark")
        return channels

    def _build_export_row(
        self,
        route_from: str,
        route_to: str,
        target_date,
        threshold: int,
        source: str,
        status: str,
        message: str,
        flight=None,
    ):
        flight = flight or {}
        price = flight.get("price", "")
        is_low_price = ""
        if isinstance(price, int):
            is_low_price = "yes" if price <= threshold else "no"

        return {
            "route_from": route_from,
            "route_to": route_to,
            "flight_date": target_date.isoformat(),
            "flight_no": flight.get("flight_no", ""),
            "airline": flight.get("airline", ""),
            "price": price,
            "threshold": threshold,
            "is_low_price": is_low_price,
            "source": source,
            "departure_time": flight.get("metadata", {}).get("departure_time", ""),
            "arrival_time": flight.get("metadata", {}).get("arrival_time", ""),
            "departure_airport": flight.get("departure_airport", ""),
            "arrival_airport": flight.get("arrival_airport", ""),
            "status": status,
            "message": message,
        }

    async def close(self) -> None:
        logger.info("关闭监控...")
        for crawler in self.crawlers.values():
            await crawler.close()
        if self.db:
            await self.db.close()
        logger.info("监控已关闭")


async def main() -> None:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.yaml")

    if not config_path.exists():
        print(f"配置文件不存在: {config_path}")
        print("请先复制 config.example.yaml 为 config.yaml 并修改配置")
        sys.exit(1)

    monitor = FlightMonitor(config_path)

    def signal_handler(sig, frame):
        print("\n收到退出信号...")
        asyncio.create_task(monitor.close())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await monitor.init()
        await monitor.run_check()
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as exc:
        logger.exception("运行错误: %s", exc)
        sys.exit(1)
    finally:
        await monitor.close()


if __name__ == "__main__":
    asyncio.run(main())
