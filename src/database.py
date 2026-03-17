"""
数据库模块
"""

import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import aiosqlite
from src.exceptions import DatabaseError
from src.utils import logger


class Database:
    """SQLite 数据库管理器"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        """初始化数据库（创建表）"""
        async with self._get_connection() as db:
            await db.executescript(self._get_schema())
            await db.commit()
        await self.migrate_add_source_column()

    @asynccontextmanager
    async def _get_connection(self):
        """获取数据库连接"""
        db = None
        try:
            db = await aiosqlite.connect(self.db_path)
            db.row_factory = aiosqlite.Row
            yield db
        finally:
            if db:
                await db.close()

    def _get_schema(self) -> str:
        """获取数据库Schema"""
        return '''
        -- 价格历史记录表
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_from TEXT NOT NULL,
            route_to TEXT NOT NULL,
            flight_date DATE NOT NULL,
            flight_no TEXT,
            airline TEXT,
            price INTEGER NOT NULL,
            check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_price_route ON price_history(route_from, route_to);
        CREATE INDEX IF NOT EXISTS idx_price_date ON price_history(flight_date);

        -- 低价提醒记录表
        CREATE TABLE IF NOT EXISTS low_price_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_from TEXT NOT NULL,
            route_to TEXT NOT NULL,
            flight_date DATE NOT NULL,
            flight_no TEXT,
            airline TEXT,
            price INTEGER NOT NULL,
            threshold INTEGER NOT NULL,
            alert_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notified BOOLEAN DEFAULT FALSE,
            notification_channels TEXT
        );

        -- 执行日志表
        CREATE TABLE IF NOT EXISTS execution_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            route_from TEXT,
            route_to TEXT,
            flight_date TEXT,
            status TEXT NOT NULL,
            message TEXT,
            execution_time_ms INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        '''

    async def migrate_add_source_column(self) -> None:
        """Migration to add source column to all tables"""
        async with self._get_connection() as db:
            for table in ['price_history', 'low_price_alerts', 'execution_logs']:
                try:
                    await db.execute(f"ALTER TABLE {table} ADD COLUMN source TEXT DEFAULT 'ctrip'")
                    logger.info(f"Added source column to {table}")
                except aiosqlite.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_price_source ON price_history(source)",
                "CREATE INDEX IF NOT EXISTS idx_alert_source ON low_price_alerts(source)",
                "CREATE INDEX IF NOT EXISTS idx_log_source ON execution_logs(source)"
            ]
            for index_sql in indexes:
                try:
                    await db.execute(index_sql)
                except aiosqlite.OperationalError:
                    pass
            await db.commit()

    async def save_price_history(
        self,
        route_from: str,
        route_to: str,
        flight_date: date,
        flight_no: str,
        airline: str,
        price: int
    ) -> None:
        """保存价格历史"""
        async with self._get_connection() as db:
            await db.execute('''
                INSERT INTO price_history
                (route_from, route_to, flight_date, flight_no, airline, price)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (route_from, route_to, flight_date, flight_no, airline, price))
            await db.commit()

    async def save_alert(
        self,
        route_from: str,
        route_to: str,
        flight_date: date,
        flight_no: str,
        airline: str,
        price: int,
        threshold: int,
        channels: List[str]
    ) -> None:
        """保存低价提醒"""
        async with self._get_connection() as db:
            await db.execute('''
                INSERT INTO low_price_alerts
                (route_from, route_to, flight_date, flight_no, airline, price, threshold, notification_channels)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                route_from, route_to, flight_date, flight_no, airline,
                price, threshold, ','.join(channels)
            ))
            await db.commit()

    async def log_execution(
        self,
        job_id: str,
        route_from: Optional[str],
        route_to: Optional[str],
        flight_date: Optional[str],
        status: str,
        message: Optional[str] = None,
        execution_time_ms: Optional[int] = None
    ) -> None:
        """记录执行日志"""
        async with self._get_connection() as db:
            await db.execute('''
                INSERT INTO execution_logs
                (job_id, route_from, route_to, flight_date, status, message, execution_time_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (job_id, route_from, route_to, flight_date, status, message, execution_time_ms))
            await db.commit()
