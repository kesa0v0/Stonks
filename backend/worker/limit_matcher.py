import asyncio
import json
import signal
import redis.asyncio as redis
from sqlalchemy import select, or_
from backend.core.config import settings
from backend.core.database import AsyncSessionLocal
from backend.models import Order, OrderStatus, OrderSide, OrderType
from backend.services.trade_service import execute_trade
from backend.worker.order_cache import LimitOrderCache

async def match_orders():
    # Redis 연결
    redis_client = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)
    price_pubsub = redis_client.pubsub()
    event_pubsub = redis_client.pubsub()
    
    # 캐시 초기화
    cache = LimitOrderCache(redis_client)
    await cache.hydrate_all_pending()
    
    # Graceful Shutdown Setup
    stop_event = asyncio.Event()

    async def shutdown():
        print("\n🛑 Received Shutdown Signal. Stopping Matcher...")
        stop_event.set()
        # Unsubscribe and close to break the loops
        if price_pubsub:
            await price_pubsub.unsubscribe()
            await price_pubsub.close()
        if event_pubsub:
            await event_pubsub.unsubscribe()
            await event_pubsub.close()
        if redis_client:
            await redis_client.aclose()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    await price_pubsub.subscribe("market_updates")
    await event_pubsub.subscribe("trade_events")

    print("⚖️ Order Matcher Started! Watching for Limit & Stop-Loss triggers... (Press CTRL+C to stop)")

    async def handle_order_events():
        try:
            async for message in event_pubsub.listen():
                if stop_event.is_set(): break
                if message['type'] != 'message':
                    continue
                try:
                    evt = json.loads(message['data'])
                except Exception:
                    continue
                evt_type = evt.get("type")
                order_id = evt.get("order_id")
                ticker_id = evt.get("ticker_id")
                if not order_id:
                    continue
                if evt_type in {"order_created", "order_accepted"}:
                    await cache.hydrate_from_db(order_id)
                elif evt_type in {"order_cancelled", "trade_executed"}:
                    await cache.remove_order(order_id, ticker_id)
        except (redis.ConnectionError, asyncio.CancelledError):
            pass # Expected on shutdown
        except Exception as e:
            print(f"⚠️ Event Loop Error: {e}")

    async def handle_prices():
        try:
            async for message in price_pubsub.listen():
                if stop_event.is_set(): break
                if message['type'] != 'message':
                    continue

                data = json.loads(message['data'])
                ticker_id = data['ticker_id']
                current_price = float(data['price'])
                
                # 비동기 DB 세션 생성 (체결 및 트레일링 스탑 업데이트용)
                async with AsyncSessionLocal() as db:
                    try:
                        # 1. LIMIT Candidates (Redis)
                        buy_limit_ids = await cache.fetch_candidates(ticker_id, OrderSide.BUY, current_price, "LIMIT")
                        sell_limit_ids = await cache.fetch_candidates(ticker_id, OrderSide.SELL, current_price, "LIMIT")
                        
                        # 2. STOP Candidates (Redis)
                        buy_stop_ids = await cache.fetch_candidates(ticker_id, OrderSide.BUY, current_price, "STOP")
                        sell_stop_ids = await cache.fetch_candidates(ticker_id, OrderSide.SELL, current_price, "STOP")

                        # Combine all candidates
                        all_candidates = set(buy_limit_ids + sell_limit_ids + buy_stop_ids + sell_stop_ids)
                        
                        if all_candidates:
                            for order_id in all_candidates:
                                if stop_event.is_set(): break # Stop processing mid-batch
                                
                                order_data = await cache.get_order_data(order_id)
                                if not order_data:
                                    continue
                                
                                # Parse Data
                                o_side = OrderSide(order_data["side"])
                                o_type = OrderType(order_data["type"])
                                o_status = OrderStatus(order_data["status"])
                                o_qty = float(order_data["quantity"])
                                o_ticker = order_data["ticker_id"]
                                
                                if o_status != OrderStatus.PENDING:
                                    continue
                                    
                                # Check Conditions
                                matched = False
                                trigger_price = 0.0
                                
                                if o_type == OrderType.LIMIT:
                                    target = float(order_data["target_price"])
                                    if o_side == OrderSide.BUY and target >= current_price:
                                        matched = True
                                        trigger_price = target
                                    elif o_side == OrderSide.SELL and target <= current_price:
                                        matched = True
                                        trigger_price = target
                                        
                                elif o_type in [OrderType.STOP_LOSS, OrderType.TAKE_PROFIT, OrderType.STOP_LIMIT, OrderType.TRAILING_STOP]:
                                    stop = float(order_data["stop_price"])
                                    
                                    if o_side == OrderSide.BUY:
                                        if current_price >= stop:
                                            matched = True
                                            trigger_price = stop
                                    else: # SELL
                                        if current_price <= stop:
                                            matched = True
                                            trigger_price = stop

                                if matched:
                                    if o_type == OrderType.STOP_LIMIT:
                                        print(f"   >> Triggering STOP_LIMIT Order {order_id}. Converting to LIMIT at {order_data['target_price']}")
                                        stmt = select(Order).where(Order.id == order_id)
                                        db_order = (await db.execute(stmt)).scalars().first()
                                        if db_order and db_order.status == OrderStatus.PENDING:
                                            db_order.type = OrderType.LIMIT
                                            await db.commit()
                                            await cache.remove_order(order_id, o_ticker)
                                            await cache.add_order(db_order) 
                                        continue

                                    print(f"   >> Triggering {o_type.value} Order {order_id} ({o_side.value}) @ {current_price} (Trigger: {trigger_price})")
                                    
                                    success = await execute_trade(
                                        db=db,
                                        redis_client=redis_client,
                                        user_id=order_data["user_id"],
                                        order_id=order_id,
                                        ticker_id=o_ticker,
                                        side=o_side.value,
                                        quantity=o_qty
                                    )
                                    
                                    if success:
                                        print(f"   ✅ Order Executed!")
                                        await cache.remove_order(order_id, o_ticker)
                                    else:
                                        print(f"   ❌ Execution Failed")

                        # --- Trailing Stop UPDATE Logic ---
                        # Keep DB Scan for safety (requires high_water_mark state)
                        ts_sell_stmt = select(Order).where(
                            Order.ticker_id == ticker_id,
                            Order.status == OrderStatus.PENDING,
                            Order.side == OrderSide.SELL,
                            Order.type == OrderType.TRAILING_STOP
                        )
                        ts_sells = (await db.execute(ts_sell_stmt)).scalars().all()
                        
                        for order in ts_sells:
                            if stop_event.is_set(): break
                            new_stop = current_price - float(order.trailing_gap)
                            if new_stop > float(order.stop_price):
                                print(f"   >> Updating Trailing Stop Sell {order.id}: {order.stop_price} -> {new_stop}")
                                order.stop_price = new_stop
                                order.high_water_mark = current_price
                                await db.commit()
                                await cache.add_order(order)
                        
                        ts_buy_stmt = select(Order).where(
                            Order.ticker_id == ticker_id,
                            Order.status == OrderStatus.PENDING,
                            Order.side == OrderSide.BUY,
                            Order.type == OrderType.TRAILING_STOP
                        )
                        ts_buys = (await db.execute(ts_buy_stmt)).scalars().all()
                        
                        for order in ts_buys:
                            if stop_event.is_set(): break
                            new_stop = current_price + float(order.trailing_gap)
                            if new_stop < float(order.stop_price):
                                print(f"   >> Updating Trailing Stop Buy {order.id}: {order.stop_price} -> {new_stop}")
                                order.stop_price = new_stop
                                order.high_water_mark = current_price
                                await db.commit()
                                await cache.add_order(order)

                    except Exception as e:
                        print(f"🔥 Matcher Error: {e}")
                        import traceback
                        traceback.print_exc()
        except (redis.ConnectionError, asyncio.CancelledError):
            pass # Expected on shutdown

    await asyncio.gather(handle_prices(), handle_order_events())
    print("👋 Matcher Stopped.")

if __name__ == "__main__":
    asyncio.run(match_orders())