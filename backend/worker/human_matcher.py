import asyncio
import logging
import redis.asyncio as redis
from decimal import Decimal
from sqlalchemy import select
from backend.core.database import AsyncSessionLocal
from backend.core.config import settings
from backend.core.enums import OrderStatus, OrderSide, OrderType
from backend.models import Order, Ticker, MarketType, Candle # Import Candle model
from backend.services.trade_service import execute_p2p_trade
from sqlalchemy.dialects.postgresql import insert # Import insert for upsert logic
from backend.schemas.market import OrderBookResponse, OrderBookEntry # Import orderbook schemas
from backend.services.market_service import publish_current_orderbook_snapshot # Import shared utility

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("human_matcher")

async def update_candle_data(db: AsyncSession, ticker_id: str, trade_price: Decimal, trade_quantity: Decimal, trade_timestamp: datetime):
    """
    주문 체결 시 1분봉 및 일봉 캔들 데이터를 업데이트하거나 새로 생성합니다.
    """
    # 1분봉 처리
    # 현재 분의 시작 시간을 계산 (UTC 기준)
    minute_start = trade_timestamp.replace(second=0, microsecond=0)
    await _upsert_candle(db, ticker_id, '1m', minute_start, trade_price, trade_quantity)

    # 일봉 처리
    # 현재 날짜의 시작 시간을 계산 (UTC 기준)
    day_start = trade_timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    await _upsert_candle(db, ticker_id, '1d', day_start, trade_price, trade_quantity)

async def _upsert_candle(db: AsyncSession, ticker_id: str, interval: str, timestamp: datetime, price: Decimal, quantity: Decimal):
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
    # db.commit()는 외부에서 처리 (match_human_orders 내에서 AsyncSessionLocal() 사용)

async def match_human_orders():
    print("🤝 Human ETF Matcher Started! Polling for P2P matches...")
    
    # Redis connection for execute_p2p_trade (event publishing)
    redis_client = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)
    
    try:
        while True:
            # 1초마다 폴링
            await asyncio.sleep(1)

            async with AsyncSessionLocal() as db:
                # 1. Find all HUMAN tickers
                tickers_stmt = select(Ticker.id).where(Ticker.market_type == MarketType.HUMAN)
                tickers = (await db.execute(tickers_stmt)).scalars().all()
                
                if not tickers:
                    continue

                for ticker_id in tickers:
                    # 각 Ticker에 대해 매칭 가능한 주문이 있는지 반복 확인 (Drain Logic)
                    # 매칭이 발생하면 다시 DB를 조회하여 연속 체결 처리
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
                            if o.type == OrderType.MARKET: return float('inf')
                            return float(o.target_price) if o.target_price is not None else 0
                            
                        def get_sell_price(o):
                            if o.type == OrderType.MARKET: return 0
                            return float(o.target_price) if o.target_price is not None else float('inf')

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
                            # execute_p2p_trade 내부에서 commit을 수행하므로, 현재 session 객체들은 expire 될 수 있음.
                            # 따라서 IDs만 넘기고, 성공 후에는 loop를 다시 시작(re-fetch)함.
                            success = await execute_p2p_trade(
                                db=db,
                                redis_client=redis_client,
                                buy_order_id=best_buy.id,
                                sell_order_id=best_sell.id,
                                match_price=Decimal(str(match_price)),
                                match_quantity=Decimal(str(match_qty))
                            )
                            
                            if success:
                                # 캔들 데이터 업데이트
                                from datetime import datetime, timezone # Import for now()
                                await update_candle_data(db, ticker_id, Decimal(str(match_price)), Decimal(str(match_qty)), datetime.now(timezone.utc))
                                
                                # 매칭 후 호가창 업데이트 발행
                                await publish_current_orderbook_snapshot(db, redis_client, ticker_id)

                                has_match = True # 매칭 성공했으니 다시 조회하여 추가 체결 시도
                            else:
                                has_match = False # 실패 시 루프 탈출 (무한 루프 방지)
                        else:
                            # No more matches possible
                            has_match = False

    except Exception as e:
        logger.error(f"Matcher Critical Error: {e}", exc_info=True)
    finally:
        await redis_client.close()

if __name__ == "__main__":
    asyncio.run(match_human_orders())
