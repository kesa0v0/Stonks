import asyncio
import logging
import json
import signal
import redis.asyncio as redis
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import select, func
from backend.core.database import AsyncSessionLocal
from backend.core.config import settings
from backend.core.enums import OrderStatus, OrderSide, OrderType
from backend.models import Order, Ticker, MarketType, Candle
from backend.services.trade_service import execute_p2p_trade
from sqlalchemy.dialects.postgresql import insert
from backend.schemas.market import OrderBookResponse, OrderBookEntry
from backend.services.market_service import publish_current_orderbook_snapshot

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("human_matcher")

async def update_candle_data(db: AsyncSessionLocal, ticker_id: str, trade_price: Decimal, trade_quantity: Decimal, trade_timestamp: datetime):
    """
    주문 체결 시 1분봉 및 일봉 캔들 데이터를 업데이트하거나 새로 생성합니다.
    """
    # 1분봉 처리
    minute_start = trade_timestamp.replace(second=0, microsecond=0)
    await _upsert_candle(db, ticker_id, '1m', minute_start, trade_price, trade_quantity)

    # 일봉 처리
    day_start = trade_timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    await _upsert_candle(db, ticker_id, '1d', day_start, trade_price, trade_quantity)

async def _upsert_candle(db: AsyncSessionLocal, ticker_id: str, interval: str, timestamp: datetime, price: Decimal, quantity: Decimal):
    """
    단일 캔들 (1분봉 또는 일봉)을 업데이트하거나 새로 생성하는 내부 헬퍼 함수
    """
    stmt = insert(Candle).values(
        ticker_id=ticker_id,
        timestamp=timestamp,
        interval=interval,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=quantity
    ).on_conflict_do_update(
        index_elements=['ticker_id', 'timestamp', 'interval'],
        set_={
            'high': func.greatest(Candle.high, price),
            'low': func.least(Candle.low, price),
            'close': price,
            'volume': Candle.volume + quantity
        }
    )
    await db.execute(stmt)

async def process_ticker_match(ticker_id: str, redis_client: redis.Redis):
    """
    단일 Ticker에 대한 매칭 로직을 수행합니다.
    """
    async with AsyncSessionLocal() as db:
        # 각 Ticker에 대해 매칭 가능한 주문이 있는지 반복 확인 (Drain Logic)
        has_match = True
        while has_match:
            has_match = False # Reset flag

            # 2. Fetch Pending Orders
            orders_stmt = select(Order).where(
                Order.ticker_id == ticker_id,
                Order.status == OrderStatus.PENDING
            ).order_by(Order.created_at.asc())
            
            orders = (await db.execute(orders_stmt)).scalars().all()
            
            if not orders:
                break
                
            buy_orders = []
            sell_orders = []
            
            for o in orders:
                if o.side == OrderSide.BUY:
                    buy_orders.append(o)
                else:
                    sell_orders.append(o)
            
            if not buy_orders or not sell_orders:
                break
            
            # 3. Sort for Matching Priority
            def get_buy_price(o):
                if o.type == OrderType.MARKET: return Decimal('inf')
                return o.target_price if o.target_price is not None else Decimal('0')
                
            def get_sell_price(o):
                if o.type == OrderType.MARKET: return Decimal('0')
                return o.target_price if o.target_price is not None else Decimal('inf')

            # Buy: Price High -> Low, Time Old -> New
            buy_orders.sort(key=lambda x: (-get_buy_price(x), x.created_at))
            # Sell: Price Low -> High, Time Old -> New
            sell_orders.sort(key=lambda x: (get_sell_price(x), x.created_at))
            
            best_buy = buy_orders[0]
            best_sell = sell_orders[0]
            
            buy_price_val = get_buy_price(best_buy)
            sell_price_val = get_sell_price(best_sell)
            
            # 4. Check Match Condition
            if buy_price_val >= sell_price_val:
                
                match_price = None
                
                # Determine Match Price
                if best_buy.type == OrderType.LIMIT and best_sell.type == OrderType.LIMIT:
                    # Both Limit: The Maker (older order) sets the price
                    if best_buy.created_at < best_sell.created_at:
                        match_price = best_buy.target_price
                    else:
                        match_price = best_sell.target_price
                elif best_buy.type == OrderType.LIMIT:
                    # Sell is Market -> Takes Buy Limit Price
                    match_price = best_buy.target_price
                elif best_sell.type == OrderType.LIMIT:
                    # Buy is Market -> Takes Sell Limit Price
                    match_price = best_sell.target_price
                else:
                    # Both Market: Skip for now (needs reference price logic)
                    logger.warning(f"Market-Market Match Skipped for {ticker_id} (No reference price)")
                    break
                    
                # Calculate Match Quantity
                match_qty = min(best_buy.unfilled_quantity, best_sell.unfilled_quantity)
                
                logger.info(f"⚡ Match Found! {ticker_id}: {match_qty} @ {match_price} (Buy {best_buy.id} vs Sell {best_sell.id})")

                # 5. Execute Trade
                success = await execute_p2p_trade(
                    db=db,
                    redis_client=redis_client,
                    buy_order_id=best_buy.id,
                    sell_order_id=best_sell.id,
                    match_price=match_price,
                    match_quantity=match_qty
                )
                
                if success:
                    # 캔들 데이터 업데이트
                    await update_candle_data(db, ticker_id, match_price, match_qty, datetime.now(timezone.utc))
                    
                    # 매칭 후 호가창 업데이트 발행
                    await publish_current_orderbook_snapshot(db, redis_client, ticker_id)

                    has_match = True # 매칭 성공했으니 다시 조회하여 추가 체결 시도
                else:
                    has_match = False # 실패 시 루프 탈출 (무한 루프 방지)
            else:
                # No more matches possible
                has_match = False

class TickerMatchScheduler:
    def __init__(self):
        self.processing_tickers = set()
        self.queued_tickers = set()
        self._lock = asyncio.Lock() # Protect set access (though GIL makes simple set ops thread-safe, async context needs care)

    async def trigger(self, ticker_id: str, redis_client: redis.Redis):
        async with self._lock:
            if ticker_id in self.processing_tickers:
                self.queued_tickers.add(ticker_id)
                return
            self.processing_tickers.add(ticker_id)
        
        # Start worker without awaiting (fire and forget)
        asyncio.create_task(self._process(ticker_id, redis_client))

    async def _process(self, ticker_id: str, redis_client: redis.Redis):
        try:
            while True:
                # Perform matching
                await process_ticker_match(ticker_id, redis_client)
                
                # Check if we need to run again
                async with self._lock:
                    if ticker_id in self.queued_tickers:
                        self.queued_tickers.remove(ticker_id)
                        # Continue loop to process again
                    else:
                        self.processing_tickers.remove(ticker_id)
                        break
        except Exception as e:
            logger.error(f"Scheduler Worker Error for {ticker_id}: {e}", exc_info=True)
            # Ensure cleanup on error
            async with self._lock:
                if ticker_id in self.processing_tickers:
                    self.processing_tickers.remove(ticker_id)
                if ticker_id in self.queued_tickers:
                    self.queued_tickers.remove(ticker_id)

async def match_human_orders():
    # Redis connection
    redis_client = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)
    pubsub = redis_client.pubsub()
    
    scheduler = TickerMatchScheduler()
    
    # Graceful Shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    
    def signal_handler():
        print("\n🛑 Received Shutdown Signal. Stopping Human Matcher...")
        stop_event.set()
        asyncio.create_task(pubsub.close())
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    await pubsub.subscribe("trade_events")
    print("🤝 Human ETF Matcher Started! Watching 'trade_events' for P2P triggers...")

    try:
        async for message in pubsub.listen():
            if stop_event.is_set():
                break
                
            if message['type'] != 'message':
                continue
                
            try:
                data = json.loads(message['data'])
                event_type = data.get("type")
                ticker_id = data.get("ticker_id")
                
                # Filter for relevant events and Human ETF tickers
                if (event_type in ["order_created", "order_accepted", "trade_executed"] and 
                    ticker_id and ticker_id.startswith("HUMAN-")):
                    
                    # Use Scheduler to ensure sequential processing per ticker
                    await scheduler.trigger(ticker_id, redis_client)
                    
            except Exception as e:
                logger.error(f"Event processing error: {e}")
                
    except (redis.ConnectionError, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.error(f"Matcher Critical Error: {e}", exc_info=True)
    finally:
        await redis_client.close()
        print("👋 Human Matcher Stopped.")

if __name__ == "__main__":
    asyncio.run(match_human_orders())
