#!/usr/bin/env python3
"""
FlightFind - 携程机票价格监控工具

用法:
    python main.py [config_path]

参数:
    config_path: 配置文件路径，默认为 config.yaml
"""

import sys
import asyncio
import signal
from pathlib import Path
from datetime import datetime
from typing import List
from src.config import load_config, Route
from src.database import Database
from src.crawler import CtripCrawler
from src.feizhu_crawler import FeizhuCrawler
from src.notifier import Notifier
from src.utils import setup_logging
import logging

logger = logging.getLogger(__name__)


class FlightMonitor:
    """机票监控主类"""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = None
        self.db = None
        self.crawler = None
        self.notifier = None
        self.running = False

    async def init(self) -> None:
        """初始化"""
        # 加载配置
        self.config = load_config(self.config_path)

        # 初始化日志
        setup_logging(
            log_file=Path("logs/monitor.log"),
            level=logging.INFO
        )

        logger.info("=" * 50)
        logger.info("FlightFind 机票监控工具启动")
        logger.info("=" * 50)

        # 初始化数据库
        self.db = Database(Path("data/flights.db"))
        await self.db.init()
        logger.info("数据库初始化完成")

        # 初始化爬虫
        if self.config.monitor.default_source == "feizhu":
            self.crawler = FeizhuCrawler(headless=self.config.monitor.headless)
        else:
            self.crawler = CtripCrawler(headless=self.config.monitor.headless)
        await self.crawler.init()
        logger.info("浏览器初始化完成")
        logger.info(f"使用数据源: {self.config.monitor.default_source}")

        # 初始化通知器
        self.notifier = Notifier(self.config.notifications)
        logger.info("通知模块初始化完成")

        logger.info(f"配置航线数量: {len(self.config.routes)}")
        for route in self.config.routes:
            logger.info(f"  - {route.from_city} -> {route.to_city} (阈值: ¥{route.low_price_threshold})")

    async def run_check(self) -> None:
        """执行一次检查"""
        if not self.crawler:
            logger.error("爬虫未初始化")
            return

        for route in self.config.routes:
            for flight_date in route.dates.absolute_dates:
                job_id = f"{route.from_city}_{route.to_city}_{flight_date.isoformat()}"
                start_time = datetime.now()

                try:
                    logger.info(f"检查: {route.from_city} -> {route.to_city} ({flight_date})")

                    flights = await self.crawler.search_flights(route)

                    if not flights:
                        logger.warning(f"未找到航班: {route.from_city} -> {route.to_city}")
                        source = self.crawler.source if hasattr(self.crawler, 'source') else self.config.monitor.default_source
                        await self.db.log_execution(
                            job_id=job_id,
                            route_from=route.from_city,
                            route_to=route.to_city,
                            flight_date=flight_date.isoformat(),
                            status="warning",
                            message="未找到航班",
                            source=source
                        )
                        continue

                    # 保存价格历史
                    for flight in flights:
                        await self.db.save_price_history(
                            route_from=flight['route_from'],
                            route_to=flight['route_to'],
                            flight_date=flight_date,
                            flight_no=flight['flight_no'],
                            airline=flight['airline'],
                            price=flight['price'],
                            source=flight['source']
                        )

                    # 检查低价
                    low_price_flights = [
                        f for f in flights
                        if f['price'] <= route.low_price_threshold
                    ]

                    execution_time = int((datetime.now() - start_time).total_seconds() * 1000)

                    if low_price_flights:
                        logger.info(f"发现 {len(low_price_flights)} 个低价航班！")

                        await self.notifier.send_low_price_alert(
                            low_price_flights,
                            flight_date=flight_date,
                            threshold=route.low_price_threshold
                        )

                        # 保存提醒记录
                        channels = self._get_enabled_channels()
                        for flight in low_price_flights:
                            await self.db.save_alert(
                                route_from=flight['route_from'],
                                route_to=flight['route_to'],
                                flight_date=flight_date,
                                flight_no=flight['flight_no'],
                                airline=flight['airline'],
                                price=flight['price'],
                                threshold=route.low_price_threshold,
                                channels=channels,
                                source=flight['source']
                            )

                        source = self.crawler.source if hasattr(self.crawler, 'source') else self.config.monitor.default_source
                        await self.db.log_execution(
                            job_id=job_id,
                            route_from=route.from_city,
                            route_to=route.to_city,
                            flight_date=flight_date.isoformat(),
                            status="success",
                            message=f"发现 {len(low_price_flights)} 个低价航班",
                            execution_time_ms=execution_time,
                            source=source
                        )
                    else:
                        min_price = min(f['price'] for f in flights)
                        logger.info(f"最低价格: ¥{min_price} (阈值: ¥{route.low_price_threshold})")

                        source = self.crawler.source if hasattr(self.crawler, 'source') else self.config.monitor.default_source
                        await self.db.log_execution(
                            job_id=job_id,
                            route_from=route.from_city,
                            route_to=route.to_city,
                            flight_date=flight_date.isoformat(),
                            status="success",
                            message=f"最低价格: ¥{min_price}",
                            execution_time_ms=execution_time,
                            source=source
                        )

                except Exception as e:
                    logger.error(f"检查失败: {route.from_city} -> {route.to_city} - {e}")
                    source = self.crawler.source if hasattr(self.crawler, 'source') else self.config.monitor.default_source
                    await self.db.log_execution(
                        job_id=job_id,
                        route_from=route.from_city,
                        route_to=route.to_city,
                        flight_date=flight_date.isoformat(),
                        status="failed",
                        message=str(e),
                        source=source
                    )

    def _get_enabled_channels(self) -> List[str]:
        """获取启用的通知渠道"""
        channels = []
        if self.config.notifications.email.enabled:
            channels.append('email')
        if self.config.notifications.webhook.enabled:
            channels.append('webhook')
        if self.config.notifications.bark.enabled:
            channels.append('bark')
        return channels

    async def close(self) -> None:
        """清理资源"""
        logger.info("正在关闭...")

        if self.crawler:
            await self.crawler.close()

        logger.info("已关闭")


async def main():
    """主函数"""
    # 获取配置文件路径
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.yaml")

    if not config_path.exists():
        print(f"错误: 配置文件不存在: {config_path}")
        print(f"请复制 config.example.yaml 到 {config_path} 并修改")
        sys.exit(1)

    monitor = FlightMonitor(config_path)

    # 设置信号处理
    def signal_handler(sig, frame):
        print("\n收到终止信号，正在关闭...")
        asyncio.create_task(monitor.close())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 初始化
        await monitor.init()

        # 执行一次检查
        await monitor.run_check()

    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        logger.exception(f"运行时错误: {e}")
        sys.exit(1)
    finally:
        await monitor.close()


if __name__ == "__main__":
    asyncio.run(main())
