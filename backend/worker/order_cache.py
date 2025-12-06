import asyncio
import json
from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import UUID

import redis.asyncio as redis
from sqlalchemy import select
from backend.models import Order, OrderStatus, OrderSide, OrderType
from backend.core.database import AsyncSessionLocal

# Redis Key Patterns
LIMIT_KEY = "oo:limit:{ticker}:{side}"       # Sorted Set (Score=Price, Member=OrderID)
STOP_KEY = "oo:stop:{ticker}:{side}"         # Sorted Set (Score=StopPrice, Member=OrderID)
ORDER_DATA_KEY = "oo:data:{order_id}"        # Hash (Field=Attribute, Value=Value)
LOADED_TICKERS_KEY = "oo:loaded_tickers"     # Set (Member=TickerID)

class LimitOrderCache:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self._local_loaded_tickers = set()

    async def store_order_data(self, order: Order):
        """Stores full order details in Redis Hash."""
        data = {
            "id": str(order.id),
            "user_id": str(order.user_id),
            "ticker_id": order.ticker_id,
            "side": order.side.value,
            "type": order.type.value,
            "status": order.status.value,
            "quantity": str(order.quantity),
            "unfilled_quantity": str(order.unfilled_quantity),
            "target_price": str(order.target_price) if order.target_price else "",
            "stop_price": str(order.stop_price) if order.stop_price else "",
            "trailing_gap": str(order.trailing_gap) if order.trailing_gap else "",
            "high_water_mark": str(order.high_water_mark) if order.high_water_mark else "",
        }
        # Filter out empty strings to save space/cleanliness (optional, but good for parsing)
        data = {k: v for k, v in data.items() if v != ""}
        
        await self.redis.hset(ORDER_DATA_KEY.format(order_id=str(order.id)), mapping=data)

    async def get_order_data(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves order data from Redis Hash."""
        data = await self.redis.hgetall(ORDER_DATA_KEY.format(order_id=order_id))
        if not data:
            return None
        return data

    async def add_order(self, order: Order):
        """Adds order to cache (Data Hash + Index Sorted Set)."""
        if order.status != OrderStatus.PENDING:
            return

        # 1. Store Data
        await self.store_order_data(order)

        # 2. Add to Index (Sorted Set) based on Type
        # LIMIT -> LIMIT_KEY (Score = target_price)
        # STOP_LOSS, TAKE_PROFIT, STOP_LIMIT, TRAILING_STOP -> STOP_KEY (Score = stop_price)
        
        pipe = self.redis.pipeline()
        
        if order.type == OrderType.LIMIT:
            key = LIMIT_KEY.format(ticker=order.ticker_id, side=order.side.value.lower())
            score = float(order.target_price)
            pipe.zadd(key, {str(order.id): score})
            
        elif order.type in [OrderType.STOP_LOSS, OrderType.TAKE_PROFIT, OrderType.STOP_LIMIT, OrderType.TRAILING_STOP]:
            key = STOP_KEY.format(ticker=order.ticker_id, side=order.side.value.lower())
            # For Trailing Stop, stop_price changes, but initial add uses current stop_price
            if order.stop_price:
                score = float(order.stop_price)
                pipe.zadd(key, {str(order.id): score})
        
        await pipe.execute()

    # Alias for backward compatibility if needed, or replace usages
    add_limit_order = add_order

    async def remove_order(self, order_id: str, ticker_id: Optional[str] = None):
        """Removes order from all caches."""
        pipe = self.redis.pipeline()
        
        # Remove Data
        pipe.delete(ORDER_DATA_KEY.format(order_id=order_id))
        
        # Remove from Indexes (Try all potential keys if ticker known, else simple scan? Scan is slow)
        # We assume ticker_id is provided usually.
        if ticker_id:
            # We don't know the side/type easily without reading data first, 
            # but reading adds latency. Just try removing from all 4 combinations.
            # Limit Buy/Sell, Stop Buy/Sell
            keys = [
                LIMIT_KEY.format(ticker=ticker_id, side="buy"),
                LIMIT_KEY.format(ticker=ticker_id, side="sell"),
                STOP_KEY.format(ticker=ticker_id, side="buy"),
                STOP_KEY.format(ticker=ticker_id, side="sell")
            ]
            for k in keys:
                pipe.zrem(k, order_id)
        else:
            # Fallback: costly scan, or just leave it (it won't match if logic checks data).
            # But we should clean up.
            async for key in self._iter_limit_keys():
                pipe.zrem(key, order_id)
                
        await pipe.execute()

    async def ensure_ticker_loaded(self, ticker_id: str):
        """
        Lazy-loads pending orders for a specific ticker if not already loaded.
        Uses a local cache + Redis Set + Redis Lock to prevent duplicate DB hits.
        """
        if ticker_id in self._local_loaded_tickers:
            return

        # Check Redis (in case another instance loaded it)
        is_loaded = await self.redis.sismember(LOADED_TICKERS_KEY, ticker_id)
        if is_loaded:
            self._local_loaded_tickers.add(ticker_id)
            return

        # Needs loading. Acquire lock to coordinate.
        lock_key = f"oo:lock:load:{ticker_id}"
        # Use a short timeout (e.g., 5s) to avoid deadlocks if instance crashes
        async with self.redis.lock(lock_key, timeout=5, blocking_timeout=2):
            # Double-check inside lock
            if await self.redis.sismember(LOADED_TICKERS_KEY, ticker_id):
                self._local_loaded_tickers.add(ticker_id)
                return
            
            # Load from DB
            print(f"📥 Lazy Loading Orders for {ticker_id}...")
            async with AsyncSessionLocal() as db:
                stmt = select(Order).where(
                    Order.ticker_id == ticker_id,
                    Order.status == OrderStatus.PENDING,
                    Order.type.in_([
                        OrderType.LIMIT, 
                        OrderType.STOP_LOSS, 
                        OrderType.TAKE_PROFIT, 
                        OrderType.STOP_LIMIT, 
                        OrderType.TRAILING_STOP
                    ])
                )
                orders = (await db.execute(stmt)).scalars().all()
            
            if orders:
                for order in orders:
                    await self.add_order(order)
            
            # Mark as loaded
            await self.redis.sadd(LOADED_TICKERS_KEY, ticker_id)
            self._local_loaded_tickers.add(ticker_id)

    async def fetch_candidates(self, ticker_id: str, side: OrderSide, price: float, order_type_group: str = "LIMIT") -> List[str]:
        """
        Fetches candidate order IDs based on price trigger.
        order_type_group: 'LIMIT' or 'STOP'
        """
        # Ensure data is loaded for this ticker
        await self.ensure_ticker_loaded(ticker_id)

        key_pattern = LIMIT_KEY if order_type_group == "LIMIT" else STOP_KEY
        key = key_pattern.format(ticker=ticker_id, side=side.value.lower())
        
        # LIMIT BUY: target >= price -> range [price, +inf]
        # LIMIT SELL: target <= price -> range [-inf, price]
        
        # STOP BUY (Stop Loss / Trailing Buy): Trigger when Price goes UP to stop_price -> range [-inf, price] ?? 
        # Wait. Stop Buy (Short Cover): Trigger when Price goes UP to stop_price. 
        #   Current Price 100. Stop Buy at 110. Trigger when Price >= 110.
        #   So we look for orders with stop_price <= Current Price.
        #   Range: [-inf, current_price]
        
        # STOP SELL (Long Exit): Trigger when Price goes DOWN to stop_price.
        #   Current Price 100. Stop Sell at 90. Trigger when Price <= 90.
        #   So we look for orders with stop_price >= Current Price.
        #   Range: [current_price, +inf]
        
        # CAREFUL: Logic is reversed for Stop vs Limit.
        
        is_buy = (side == OrderSide.BUY)
        
        if order_type_group == "LIMIT":
            if is_buy: # Limit Buy (Low Price favored? No, executes if Market Price <= Limit Price. But here we have Last Price.)
                # Limit Buy at 100. Market Price 90. Match!
                # Condition: Limit Price >= Market Price.
                # Find orders with Score (Limit Price) >= Current Price.
                return await self.redis.zrangebyscore(key, price, "+inf")
            else: # Limit Sell
                # Limit Sell at 100. Market Price 110. Match!
                # Condition: Limit Price <= Market Price.
                # Find orders with Score (Limit Price) <= Current Price.
                return await self.redis.zrangebyscore(key, "-inf", price)
                
        elif order_type_group == "STOP":
            if is_buy: # Stop Buy (Trigger when Price rises to Stop)
                # Stop Buy at 110. Current Price 115. Trigger!
                # Condition: Stop Price <= Current Price.
                return await self.redis.zrangebyscore(key, "-inf", price)
            else: # Stop Sell (Trigger when Price falls to Stop)
                # Stop Sell at 90. Current Price 80. Trigger!
                # Condition: Stop Price >= Current Price.
                return await self.redis.zrangebyscore(key, price, "+inf")
                
        return []

    async def hydrate_from_db(self, order_id: str) -> Optional[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            stmt = select(Order).where(Order.id == order_id)
            order = (await db.execute(stmt)).scalars().first()
            if order and order.status == OrderStatus.PENDING:
                await self.add_order(order)
                return await self.get_order_data(order_id)
        return None

    async def _iter_limit_keys(self):
        cursor = "0"
        while cursor != 0:
            cursor, keys = await self.redis.scan(cursor=cursor, match="oo:*", count=100)
            for k in keys:
                yield k
