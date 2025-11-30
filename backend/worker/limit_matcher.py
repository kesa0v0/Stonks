import asyncio
import json
import redis.asyncio as redis
from sqlalchemy import select, or_
from backend.core.config import settings
from backend.core.database import AsyncSessionLocal
from backend.models import Order, OrderStatus, OrderSide, OrderType
from backend.services.trade_service import execute_trade

async def match_orders():
    # Redis 연결 (가격 구독용)
    r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe("market_updates")

    print("⚖️ Order Matcher Started! Watching for Limit & Stop-Loss triggers...")

    async for message in pubsub.listen():
        if message['type'] != 'message':
            continue

        data = json.loads(message['data'])
        ticker_id = data['ticker_id']
        current_price = float(data['price'])
        
        # 비동기 DB 세션 생성
        async with AsyncSessionLocal() as db:
            try:
                # --- 1. LIMIT 주문 매칭 (기존 로직) ---
                # Limit Buy: 목표가 >= 현재가 (가격이 떨어져서 도달)
                limit_buy_stmt = select(Order).where(
                    Order.ticker_id == ticker_id,
                    Order.status == OrderStatus.PENDING,
                    Order.side == OrderSide.BUY,
                    Order.type == OrderType.LIMIT,
                    Order.target_price >= current_price 
                )
                
                # Limit Sell: 목표가 <= 현재가 (가격이 올라서 도달)
                limit_sell_stmt = select(Order).where(
                    Order.ticker_id == ticker_id,
                    Order.status == OrderStatus.PENDING,
                    Order.side == OrderSide.SELL,
                    Order.type == OrderType.LIMIT,
                    Order.target_price <= current_price
                )

                # --- 2. STOP_LOSS 주문 매칭 (신규 로직) ---
                # Stop Buy (숏 포지션 청산): 가격이 stop_price 이상으로 오르면 발동
                # 예: 숏 진입가 10,000원 -> 11,000원 오면 손절 (Stop Buy 11,000) -> 현재가 11,005원이면 발동
                stop_buy_stmt = select(Order).where(
                    Order.ticker_id == ticker_id,
                    Order.status == OrderStatus.PENDING,
                    Order.side == OrderSide.BUY,
                    Order.type == OrderType.STOP_LOSS,
                    Order.stop_price <= current_price 
                )

                # Stop Sell (롱 포지션 청산): 가격이 stop_price 이하로 떨어지면 발동
                # 예: 롱 진입가 10,000원 -> 9,000원 오면 손절 (Stop Sell 9,000) -> 현재가 8,995원이면 발동
                stop_sell_stmt = select(Order).where(
                    Order.ticker_id == ticker_id,
                    Order.status == OrderStatus.PENDING,
                    Order.side == OrderSide.SELL,
                    Order.type == OrderType.STOP_LOSS,
                    Order.stop_price >= current_price
                )

                # --- 4. STOP_LIMIT 주문 매칭 (Trigger Only) ---
                # 발동되면 MARKET 주문처럼 바로 체결되는게 아니라, LIMIT 주문으로 변환됨 (PENDING 유지, Type 변경)
                # 여기서는 execute_trade를 호출하지 않고, 직접 상태 변경 로직을 수행해야 함.
                # 하지만 복잡도를 줄이기 위해, execute_trade가 STOP_LIMIT 처리 로직을 포함하도록 하거나,
                # 여기서 주문 타입을 LIMIT으로 바꾸고 DB 업데이트만 한 뒤, 다음 루프에서 Limit Matcher에 걸리게 할 수 있음.
                
                # Stop Limit Buy: 가격이 stop_price 이상이면 발동 -> target_price로 Limit Buy 생성
                sl_buy_stmt = select(Order).where(
                    Order.ticker_id == ticker_id,
                    Order.status == OrderStatus.PENDING,
                    Order.side == OrderSide.BUY,
                    Order.type == OrderType.STOP_LIMIT,
                    Order.stop_price <= current_price 
                )
                
                # Stop Limit Sell: 가격이 stop_price 이하이면 발동 -> target_price로 Limit Sell 생성
                sl_sell_stmt = select(Order).where(
                    Order.ticker_id == ticker_id,
                    Order.status == OrderStatus.PENDING,
                    Order.side == OrderSide.SELL,
                    Order.type == OrderType.STOP_LIMIT,
                    Order.stop_price >= current_price
                )
                
                sl_buys = (await db.execute(sl_buy_stmt)).scalars().all()
                sl_sells = (await db.execute(sl_sell_stmt)).scalars().all()
                
                # STOP_LIMIT 발동 처리 (별도 루프)
                for order in list(sl_buys) + list(sl_sells):
                    print(f"   >> Triggering STOP_LIMIT Order {order.id}. Converting to LIMIT at {order.target_price}")
                    order.type = OrderType.LIMIT
                    # status는 PENDING 유지. 이제 Limit Matcher가 다음 틱에 잡을 것임.
                    # 만약 target_price가 이미 체결 가능한 가격이라면? 다음 틱에 바로 체결됨.
                    await db.commit()

                # --- 5. TRAILING_STOP 주문 업데이트 (Update Only) ---
                # Trailing Sell: 가격이 오르면 stop_price도 오름.
                # 조건: (현재가 - gap) > stop_price
                ts_sell_stmt = select(Order).where(
                    Order.ticker_id == ticker_id,
                    Order.status == OrderStatus.PENDING,
                    Order.side == OrderSide.SELL,
                    Order.type == OrderType.TRAILING_STOP
                )
                ts_sells = (await db.execute(ts_sell_stmt)).scalars().all()
                
                for order in ts_sells:
                    new_stop = current_price - float(order.trailing_gap)
                    if new_stop > float(order.stop_price):
                        print(f"   >> Updating Trailing Stop Sell {order.id}: {order.stop_price} -> {new_stop}")
                        order.stop_price = new_stop
                        order.high_water_mark = current_price
                        await db.commit()
                
                # Trailing Buy: 가격이 내리면 stop_price도 내림.
                # 조건: (현재가 + gap) < stop_price
                ts_buy_stmt = select(Order).where(
                    Order.ticker_id == ticker_id,
                    Order.status == OrderStatus.PENDING,
                    Order.side == OrderSide.BUY,
                    Order.type == OrderType.TRAILING_STOP
                )
                ts_buys = (await db.execute(ts_buy_stmt)).scalars().all()
                
                for order in ts_buys:
                    new_stop = current_price + float(order.trailing_gap)
                    if new_stop < float(order.stop_price):
                        print(f"   >> Updating Trailing Stop Buy {order.id}: {order.stop_price} -> {new_stop}")
                        order.stop_price = new_stop
                        order.high_water_mark = current_price
                        await db.commit()

                # --- 6. TRAILING_STOP 주문 매칭 (Trigger) ---
                # 업데이트된 stop_price 기준으로 트리거 체크 (STOP_LOSS와 동일)
                
                # Trailing Sell Trigger: 가격 <= stop_price
                ts_trigger_sell_stmt = select(Order).where(
                    Order.ticker_id == ticker_id,
                    Order.status == OrderStatus.PENDING,
                    Order.side == OrderSide.SELL,
                    Order.type == OrderType.TRAILING_STOP,
                    Order.stop_price >= current_price
                )
                
                # Trailing Buy Trigger: 가격 >= stop_price
                ts_trigger_buy_stmt = select(Order).where(
                    Order.ticker_id == ticker_id,
                    Order.status == OrderStatus.PENDING,
                    Order.side == OrderSide.BUY,
                    Order.type == OrderType.TRAILING_STOP,
                    Order.stop_price <= current_price
                )
                
                ts_trigger_sells = (await db.execute(ts_trigger_sell_stmt)).scalars().all()
                ts_trigger_buys = (await db.execute(ts_trigger_buy_stmt)).scalars().all()

                matches = list(limit_buys) + list(limit_sells) + list(stop_buys) + list(stop_sells) + list(tp_buys) + list(tp_sells) + list(ts_trigger_sells) + list(ts_trigger_buys)
                
                if matches:
                    print(f"⚡ Found {len(matches)} triggers for {ticker_id} at {current_price}")
                    
                    for order in matches:
                        trigger_price = order.target_price if order.type == OrderType.LIMIT else order.stop_price
                        order_type_str = "Limit" if order.type == OrderType.LIMIT else "Stop-Loss"
                        print(f"   >> Triggering {order_type_str} Order {order.id} ({order.side}) Target/Stop: {trigger_price}")
                        
                        # 비동기 실행 (execute_trade는 시장가처럼 처리함)
                        success = await execute_trade(
                            db=db,
                            redis_client=r, # 기존 redis 클라이언트 재사용
                            user_id=str(order.user_id),
                            order_id=str(order.id),
                            ticker_id=order.ticker_id,
                            side=order.side.value, # Enum -> str
                            quantity=float(order.quantity)
                        )
                        
                        if success:
                            print(f"   ✅ Order Executed!")
                        else:
                            print(f"   ❌ Execution Failed (Balance/Stock insufficient)")
                            # 실패 시 FAILED 처리 로직은 execute_trade 안에 있음

            except Exception as e:
                print(f"🔥 Matcher Error: {e}")
            # finally: await db.close()는 async with가 자동으로 처리함

if __name__ == "__main__":
    asyncio.run(match_orders())