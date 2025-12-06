import asyncio
from typing import List, Optional

import redis.asyncio as redis
from sqlalchemy import select
from backend.models import Order, OrderStatus, OrderSide, OrderType
from backend.core.database import AsyncSessionLocal

LIMIT_KEY = "oo:limit:{ticker}:{side}"

class LimitOrderCache:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def add_limit_order(self, order: Order):
        if order.type != OrderType.LIMIT or order.status != OrderStatus.PENDING:
            return
        key = LIMIT_KEY.format(ticker=order.ticker_id, side=order.side.value.lower())
        score = float(order.target_price)
        await self.redis.zadd(key, {str(order.id): score})

    async def remove_order(self, order_id: str, ticker_id: Optional[str] = None):
        # If ticker unknown, try both sides/all tickers (slower but safe)
        if ticker_id:
            await asyncio.gather(
                self.redis.zrem(LIMIT_KEY.format(ticker=ticker_id, side="buy"), order_id),
                self.redis.zrem(LIMIT_KEY.format(ticker=ticker_id, side="sell"), order_id),
            )
        else:
            # Fallback scan over keys
            async for key in self._iter_limit_keys():
                await self.redis.zrem(key, order_id)

    async def fetch_candidates(self, ticker_id: str, side: OrderSide, current_price: float) -> List[str]:
        key = LIMIT_KEY.format(ticker=ticker_id, side=side.value.lower())
        if side == OrderSide.BUY:
            # Trigger when target_price >= current_price
            ids = await self.redis.zrangebyscore(key, current_price, "+inf")
        else:
            # SELL triggers when target_price <= current_price
            ids = await self.redis.zrangebyscore(key, "-inf", current_price)
        return ids or []

    async def hydrate_from_db(self, order_id: str) -> Optional[Order]:
        async with AsyncSessionLocal() as db:
            stmt = select(Order).where(Order.id == order_id)
            order = (await db.execute(stmt)).scalars().first()
            if order and order.type == OrderType.LIMIT and order.status == OrderStatus.PENDING:
                await self.add_limit_order(order)
                return order
        return None

    async def hydrate_all_pending(self):
        # Rebuild cache on startup so restart does not drop pending LIMITs
        async with AsyncSessionLocal() as db:
            stmt = select(Order).where(
                Order.type == OrderType.LIMIT,
                Order.status == OrderStatus.PENDING
            )
            orders = (await db.execute(stmt)).scalars().all()

        if not orders:
            return

        pipe = self.redis.pipeline(transaction=False)
        for order in orders:
            key = LIMIT_KEY.format(ticker=order.ticker_id, side=order.side.value.lower())
            pipe.zadd(key, {str(order.id): float(order.target_price)})
        await pipe.execute()

    async def _iter_limit_keys(self):
        cursor = "0"
        while cursor != 0:
            cursor, keys = await self.redis.scan(cursor=cursor, match="oo:limit:*", count=50)
            for k in keys:
                yield k
