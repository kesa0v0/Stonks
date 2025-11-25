# backend/worker/trade_consumer.py
import asyncio
import json
import aio_pika
from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.services.trade_service import execute_trade

async def process_message(message: aio_pika.IncomingMessage):
    async with message.process():
        # 1. 메시지 디코딩
        body = json.loads(message.body.decode())
        print(f"📩 Received Order: {body}")
        
        # 2. DB 세션 생성
        db = SessionLocal()
        
        try:
            # 3. 비즈니스 로직 실행 (동기 함수이므로, 실행 흐름을 위해 여기서 바로 호출)
            # (대규모 트래픽 처리를 위해선 run_in_executor 등을 쓰지만 지금은 직접 호출)
            success = execute_trade(
                db=db,
                user_id=body['user_id'], # 테스트용 UUID (주의: DB에 User가 먼저 있어야 함)
                order_id=body['order_id'],
                ticker_id=body['ticker_id'],
                side=body['side'],
                quantity=body['quantity']
            )
            
            if success:
                print("🎉 Order Processed Successfully")
            else:
                print("⚠️ Order Failed logic")
                
        except Exception as e:
            print(f"🔥 Critical Error processing order: {e}")
        finally:
            db.close()

async def main():
    # RabbitMQ 연결
    connection = await aio_pika.connect_robust(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        login=settings.RABBITMQ_USER,
        password=settings.RABBITMQ_PASS
    )

    async with connection:
        # 채널 생성 및 큐 선언 (API와 동일한 이름이어야 함)
        channel = await connection.channel()
        queue = await channel.declare_queue("trade_queue", durable=True)

        print("🚀 Trade Worker Started! Waiting for orders...")
        
        # 메시지 소비 시작
        await queue.consume(process_message)
        
        # 무한 대기 (워커가 죽지 않도록)
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())