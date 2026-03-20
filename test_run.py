"""
测试 CSAIR。
"""

import asyncio
import logging
from datetime import date, timedelta
from src.config import Route, DateConfig
from src.csair_crawler import CsairCrawler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s"
)

async def test_csair():
    dates = DateConfig(
        mode="absolute",
        absolute_dates=[date.today() + timedelta(days=10)]
    )
    route = Route(
        from_city="深圳",
        to_city="上海",
        low_price_threshold=500,
        dates=dates,
    )

    crawler = CsairCrawler(headless=False)

    try:
        print("初始化爬虫...")
        await crawler.init()

        print(f"搜索航班: {route.from_city} -> {route.to_city}")

        flights = await crawler.search_flights(route)

        print(f"\n成功获取 {len(flights)} 个航班:")
        for flight in flights[:5]:
            print(f"  {flight['flight_no']} | {flight['price']}元")

    except Exception as e:
        print(f"测试失败: {e}")
    finally:
        print("关闭爬虫...")
        try:
            await crawler.close()
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(test_csair())
