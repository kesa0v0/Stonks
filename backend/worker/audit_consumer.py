# backend/worker/audit_consumer.py
import asyncio
import json
import signal
import logging
import aio_pika
from backend.core.config import settings
from backend.core.database import AsyncSessionLocal
from backend.models.portfolio_history import PortfolioHistory
from backend.models.order_status_history import OrderStatusHistory

# 로깅 설정
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def process_audit_message(message: aio_pika.IncomingMessage):
    """
    Audit 로그 이벤트를 처리하여 DB에 저장합니다.
    """
    async with AsyncSessionLocal() as db:
        try:
            async with message.process():
                body = json.loads(message.body.decode())
                event_type = body.get("event_type")
                data = body.get("data")
                
                if not event_type or not data:
                    logger.warning(f"Invalid audit message format: {body}")
                    return

                if event_type == "portfolio_history":
                    # 포트폴리오 히스토리 저장
                    history = PortfolioHistory(**data)
                    db.add(history)
                    
                elif event_type == "order_status_history":
                    # 주문 상태 히스토리 저장
                    history = OrderStatusHistory(**data)
                    db.add(history)
                
                else:
                    logger.warning(f"Unknown audit event type: {event_type}")
                    return

                await db.commit()
                # logger.info(f"✅ Audit Log Saved: {event_type}") # Too verbose?

        except Exception as e:
            logger.error(f"🔥 Audit Consumer Error: {e}", exc_info=True)
            # DB 롤백은 context manager가 에러 발생 시 자동 처리하지 않으므로 명시적 호출?
            # AsyncSessionLocal 컨텍스트 매니저는 commit을 자동 호출하지 않음.
            # 에러 시 rollback은 필요함.
            await db.rollback()

async def main():
    # Shutdown Event
    stop_event = asyncio.Event()

    def shutdown():
        logger.info("\n🛑 Received Shutdown Signal. Stopping Audit Consumer...")
        stop_event.set()

    # Signal Handling
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown)

    # RabbitMQ 연결
    try:
        connection = await aio_pika.connect_robust(
            host=settings.RABBITMQ_HOST,
            port=settings.RABBITMQ_PORT,
            login=settings.RABBITMQ_USER,
            password=settings.RABBITMQ_PASS
        )
    except Exception as e:
        logger.error(f"Failed to connect to RabbitMQ: {e}")
        return

    async with connection:
        channel = await connection.channel()
        # Audit 큐 선언
        queue = await channel.declare_queue("audit_queue", durable=True)
        await channel.set_qos(prefetch_count=10) # Batch process allowed?

        logger.info("🚀 Audit Worker Started! Waiting for logs... (Press CTRL+C to stop)")
        
        consumer_tag = await queue.consume(process_audit_message)
        
        await stop_event.wait()
        
        logger.info("⏳ Closing Audit Consumer...")
        await queue.cancel(consumer_tag)
        
    logger.info("👋 Audit Worker Stopped.")

if __name__ == "__main__":
    asyncio.run(main())
