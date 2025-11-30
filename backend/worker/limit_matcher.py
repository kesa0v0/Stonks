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

                # 모든 매칭 주문 조회
                # 각각 실행하는게 쿼리는 늘어나지만 로직은 명확함. Union 사용 가능하나 ORM 복잡도 증가.
                # 간단히 순차 실행
                
                limit_buys = (await db.execute(limit_buy_stmt)).scalars().all()
                limit_sells = (await db.execute(limit_sell_stmt)).scalars().all()
                stop_buys = (await db.execute(stop_buy_stmt)).scalars().all()
                stop_sells = (await db.execute(stop_sell_stmt)).scalars().all()

                matches = list(limit_buys) + list(limit_sells) + list(stop_buys) + list(stop_sells)
                
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