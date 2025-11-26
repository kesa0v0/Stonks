import asyncio
import json
import redis.asyncio as redis
from sqlalchemy import and_
from backend.core.config import settings
from backend.core.database import SessionLocal
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
        
        # 동기 DB 세션 생성
        db = SessionLocal()
        
        try:
            # 1. 매수(BUY) 감시: 목표가 >= 현재가 (가격이 떨어져서 도달)
            buy_orders = db.query(Order).filter(
                Order.ticker_id == ticker_id,
                Order.status == OrderStatus.PENDING,
                Order.side == OrderSide.BUY,
                Order.type == OrderType.LIMIT,
                Order.target_price >= current_price # 싸게 살 기회!
            ).all()

            # 2. 매도(SELL) 감시: 목표가 <= 현재가 (가격이 올라서 도달)
            sell_orders = db.query(Order).filter(
                Order.ticker_id == ticker_id,
                Order.status == OrderStatus.PENDING,
                Order.side == OrderSide.SELL,
                Order.type == OrderType.LIMIT,
                Order.target_price <= current_price # 비싸게 팔 기회!
            ).all()

            matches = buy_orders + sell_orders
            
            if matches:
                print(f"⚡ Found {len(matches)} matchable orders for {ticker_id} at {current_price}")
                
                for order in matches:
                    print(f"   >> Executing Limit Order {order.id} (Target: {order.target_price})")
                    # 기존 시장가 체결 로직 재사용
                    # (execute_trade 함수를 조금 고쳐야 할 수도 있지만, 기본적으로 작동함)
                    success = execute_trade(
                        db=db,
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
        finally:
            db.close()

if __name__ == "__main__":
    asyncio.run(match_orders())