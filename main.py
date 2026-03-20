#!/usr/bin/env python3
"""
FlightFind entrypoint.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import List

from src.config import load_config
from src.captcha_solver import init_captcha_solver
from src.csair_crawler import CsairCrawler
from src.crawler import CtripCrawler
from src.database import Database
from src.exporter import FlightExporter
from src.feizhu_crawler import FeizhuCrawler
from src.ho_crawler import HoCrawler
from src.mu_crawler import MuCrawler
from src.notifier import Notifier
from src.spring_crawler import SpringCrawler
from src.utils import setup_logging
from src.zh_crawler import ZhCrawler

logger = logging.getLogger(__name__)


class FlightMonitor:
    """Main monitor workflow."""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = None
        self.db = None
        self.crawler = None
        self.notifier = None
        self.exporter = None

    async def init(self) -> None:
        self.config = load_config(self.config_path)

        setup_logging(log_file=Path("logs/monitor.log"), level=logging.INFO)
        logger.info("=" * 50)
        logger.info("FlightFind started")
        logger.info("=" * 50)

        # 初始化打码服务
        if self.config.captcha:
            captcha_config = {
                "type": self.config.captcha.type,
                "chaojiying_username": self.config.captcha.chaojiying_username,
                "chaojiying_password": self.config.captcha.chaojiying_password,
                "chaojiying_soft_id": self.config.captcha.chaojiying_soft_id,
            }
            init_captcha_solver(captcha_config)
            if self.config.captcha.type == "chaojiying":
                logger.info("打码服务已启用: 超级鹰")

        self.db = Database(Path("data/flights.db"))
        await self.db.init()

        if self.config.monitor.default_source == "feizhu":
            self.crawler = FeizhuCrawler(
                headless=self.config.monitor.headless,
                username=self.config.monitor.feizhu_username,
                password=self.config.monitor.feizhu_password,
            )
        elif self.config.monitor.default_source == "csair":
            self.crawler = CsairCrawler(headless=self.config.monitor.headless)
        elif self.config.monitor.default_source == "spring":
            self.crawler = SpringCrawler(headless=self.config.monitor.headless)
        elif self.config.monitor.default_source == "mu":
            self.crawler = MuCrawler(headless=self.config.monitor.headless)
        elif self.config.monitor.default_source == "zh":
            self.crawler = ZhCrawler(headless=self.config.monitor.headless)
        elif self.config.monitor.default_source == "ho":
            self.crawler = HoCrawler(headless=self.config.monitor.headless)
        else:
            self.crawler = CtripCrawler(headless=self.config.monitor.headless)
        await self.crawler.init()

        self.notifier = Notifier(self.config.notifications)
        self.exporter = FlightExporter(Path("exports"))

        logger.info("Source: %s", self.config.monitor.default_source)
        logger.info("Routes: %s", len(self.config.routes))
        for route in self.config.routes:
            logger.info(
                "  - %s -> %s, threshold=%s, dates=%s",
                route.from_city,
                route.to_city,
                route.low_price_threshold,
                len(route.dates.absolute_dates),
            )

    async def run_check(self) -> None:
        """Execute one monitoring pass."""
        if not self.crawler:
            logger.error("Crawler is not initialized")
            return

        export_rows = []

        if isinstance(self.crawler, FeizhuCrawler):
            try:
                logger.info("Phase 1/2: logging in to Fliggy...")
                await self.crawler.ensure_logged_in()
                logger.info("Phase 1/2: Fliggy login phase finished")
            except Exception as exc:
                logger.warning("Fliggy login phase failed, continue querying: %s", exc)

        logger.info("Phase 2/2: querying flights...")
        for route in self.config.routes:
            route_start = datetime.now()
            source = self.crawler.source if hasattr(self.crawler, "source") else self.config.monitor.default_source

            try:
                logger.info("Checking route %s -> %s", route.from_city, route.to_city)
                flights = await self.crawler.search_flights(route)
            except Exception as exc:
                logger.error("Route check failed: %s -> %s - %s", route.from_city, route.to_city, exc)
                for target_date in route.dates.absolute_dates:
                    export_rows.append(
                        self._build_export_row(
                            route_from=route.from_city,
                            route_to=route.to_city,
                            target_date=target_date,
                            threshold=route.low_price_threshold,
                            source=source,
                            status="failed",
                            message=str(exc),
                        )
                    )
                    await self.db.log_execution(
                        job_id=f"{route.from_city}_{route.to_city}_{target_date.isoformat()}",
                        route_from=route.from_city,
                        route_to=route.to_city,
                        flight_date=target_date.isoformat(),
                        status="failed",
                        message=str(exc),
                        source=source,
                    )
                continue

            flights_by_date = {d: [] for d in route.dates.absolute_dates}
            for flight in flights:
                flight_date = flight.get("flight_date")
                if flight_date in flights_by_date:
                    flights_by_date[flight_date].append(flight)

            channels = self._get_enabled_channels()
            execution_time = int((datetime.now() - route_start).total_seconds() * 1000)

            for target_date in route.dates.absolute_dates:
                job_id = f"{route.from_city}_{route.to_city}_{target_date.isoformat()}"
                date_flights = flights_by_date.get(target_date, [])

                if not date_flights:
                    logger.warning("No flights found: %s -> %s (%s)", route.from_city, route.to_city, target_date)
                    export_rows.append(
                        self._build_export_row(
                            route_from=route.from_city,
                            route_to=route.to_city,
                            target_date=target_date,
                            threshold=route.low_price_threshold,
                            source=source,
                            status="warning",
                            message="No flights found",
                        )
                    )
                    await self.db.log_execution(
                        job_id=job_id,
                        route_from=route.from_city,
                        route_to=route.to_city,
                        flight_date=target_date.isoformat(),
                        status="warning",
                        message="No flights found",
                        source=source,
                    )
                    continue

                sorted_date_flights = sorted(
                    date_flights,
                    key=lambda flight: (
                        flight["price"],
                        flight.get("flight_no", ""),
                        flight.get("airline", ""),
                    ),
                )
                low_price_flights = [
                    flight for flight in sorted_date_flights if flight["price"] <= route.low_price_threshold
                ]
                display_flights = low_price_flights[:] or sorted_date_flights[:1]

                for flight in display_flights:
                    message = (
                        "Below threshold"
                        if flight["price"] <= route.low_price_threshold
                        else "Above threshold; keeping lowest observed price"
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

                for flight in sorted_date_flights:
                    await self.db.save_price_history(
                        route_from=flight["route_from"],
                        route_to=flight["route_to"],
                        flight_date=target_date,
                        flight_no=flight["flight_no"],
                        airline=flight["airline"],
                        price=flight["price"],
                        source=flight["source"],
                    )

                if low_price_flights:
                    await self.notifier.send_low_price_alert(
                        low_price_flights,
                        flight_date=target_date,
                        threshold=route.low_price_threshold,
                    )

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
                    msg = f"Found {len(low_price_flights)} low-price flights"
                else:
                    min_price = sorted_date_flights[0]["price"]
                    msg = f"No prices matched threshold; lowest observed price kept: {min_price}"

                await self.db.log_execution(
                    job_id=job_id,
                    route_from=route.from_city,
                    route_to=route.to_city,
                    flight_date=target_date.isoformat(),
                    status="success",
                    message=msg,
                    execution_time_ms=execution_time,
                    source=source,
                )

        if self.exporter:
            export_path = self.exporter.export_run_summary(export_rows)
            logger.info("Run summary exported to %s", export_path)

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

        row_message = message
        if flight.get("metadata", {}).get("record_type") == "daily_min_price_calendar":
            row_message = f"{message}; daily minimum price calendar"

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
            "message": row_message,
        }

    async def close(self) -> None:
        logger.info("Closing monitor...")
        if self.crawler:
            await self.crawler.close()
        if self.db:
            await self.db.close()
        logger.info("Monitor closed")


async def main() -> None:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.yaml")

    if not config_path.exists():
        print(f"Config not found: {config_path}")
        print("Copy config.example.yaml to config.yaml first.")
        sys.exit(1)

    monitor = FlightMonitor(config_path)

    def signal_handler(sig, frame):
        print("\nSignal received, shutting down...")
        asyncio.create_task(monitor.close())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await monitor.init()
        await monitor.run_check()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as exc:
        logger.exception("Runtime error: %s", exc)
        sys.exit(1)
    finally:
        await monitor.close()


if __name__ == "__main__":
    asyncio.run(main())
