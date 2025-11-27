import asyncio
import json
import redis.asyncio as redis
from sqlalchemy import select
from backend.core.config import settings
from backend.core.database import AsyncSessionLocal
from backend.models import Order, OrderStatus, OrderSide, OrderType
from backend.services.trade_service import execute_trade

async def match_orders():
    # Redis 연결 (가격 구독용)
    r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe("market_updates")

    print("⚖️ Limit Matcher Started! Watching for price movements...")

    async for message in pubsub.listen():
        if message['type'] != 'message':
            continue

        data = json.loads(message['data'])
        ticker_id = data['ticker_id']
        current_price = float(data['price'])
        
        # 비동기 DB 세션 생성
        async with AsyncSessionLocal() as db:
            try:
                # 1. 매수(BUY) 감시: 목표가 >= 현재가 (가격이 떨어져서 도달)
                buy_stmt = select(Order).where(
                    Order.ticker_id == ticker_id,
                    Order.status == OrderStatus.PENDING,
                    Order.side == OrderSide.BUY,
                    Order.type == OrderType.LIMIT,
                    Order.target_price >= current_price # 싸게 살 기회!
                )
                buy_result = await db.execute(buy_stmt)
                buy_orders = buy_result.scalars().all()

                # 2. 매도(SELL) 감시: 목표가 <= 현재가 (가격이 올라서 도달)
                sell_stmt = select(Order).where(
                    Order.ticker_id == ticker_id,
                    Order.status == OrderStatus.PENDING,
                    Order.side == OrderSide.SELL,
                    Order.type == OrderType.LIMIT,
                    Order.target_price <= current_price # 비싸게 팔 기회!
                )
                sell_result = await db.execute(sell_stmt)
                sell_orders = sell_result.scalars().all()

                matches = list(buy_orders) + list(sell_orders)
                
                if matches:
                    print(f"⚡ Found {len(matches)} matchable orders for {ticker_id} at {current_price}")
                    
                    for order in matches:
                        print(f"   >> Executing Limit Order {order.id} (Target: {order.target_price})")
                        # 비동기 실행
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
                            print(f"   ✅ Limit Order Filled!")
                        else:
                            print(f"   ❌ Execution Failed (Balance/Stock insufficient)")
                            # 실패 시 FAILED 처리 로직은 execute_trade 안에 있음

            except Exception as e:
                print(f"🔥 Matcher Error: {e}")
            # finally: await db.close()는 async with가 자동으로 처리함

if __name__ == "__main__":
    asyncio.run(match_orders())
