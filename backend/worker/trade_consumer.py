# backend/worker/trade_consumer.py
import asyncio
import json
import signal
import aio_pika
import redis.asyncio as async_redis
from backend.core.config import settings
from backend.core.database import AsyncSessionLocal
from backend.services.trade_service import execute_trade

async def process_message(message: aio_pika.IncomingMessage):
    # 비동기 세션 생성
    async with AsyncSessionLocal() as db:
        redis_client = None # 초기화
        try:
            async with message.process():
                # 1. 메시지 디코딩
                body = json.loads(message.body.decode())
                print(f"📩 Received Order: {body}")
                
                # 2. Redis 클라이언트 생성 (메시지 처리당 하나씩)
                redis_client = async_redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    decode_responses=True
                )
                
                # 3. 비즈니스 로직 실행 (비동기 함수이므로 await 사용)
                success = await execute_trade(
                    db=db,
                    redis_client=redis_client,
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
            if redis_client:
                await redis_client.close()
        # db.close()는 async with가 자동 처리

async def main():
    # Shutdown Event
    stop_event = asyncio.Event()

    def shutdown():
        print("\n🛑 Received Shutdown Signal. Stopping Consumer...")
        stop_event.set()

    # Signal Handling
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown)

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
        # Prefetch count 1 to ensure fair dispatch and safe shutdown (don't buffer too many unacked messages)
        await channel.set_qos(prefetch_count=1)

        print("🚀 Trade Worker Started! Waiting for orders... (Press CTRL+C to stop)")
        
        # 메시지 소비 시작
        consumer_tag = await queue.consume(process_message)
        
        # Wait for shutdown signal
        await stop_event.wait()
        
        print("⏳ Closing Consumer and Connection...")
        # Cancel consumer to stop receiving new messages
        await queue.cancel(consumer_tag)
        
        # Allow some time for active tasks to complete if necessary?
        # aio_pika's async with connection block handles graceful close, 
        # but explicit close helps ensure we don't kill mid-process.
        
    print("👋 Trade Worker Stopped.")

if __name__ == "__main__":
    asyncio.run(main())