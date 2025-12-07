# backend/core/audit.py
import json
import aio_pika
import logging
from backend.core.config import settings

logger = logging.getLogger(__name__)

async def publish_audit_log(event_type: str, data: dict):
    """
    Publishes an audit log message to the RabbitMQ 'audit_queue'.
    Opens a new connection for each publish to ensure robustness in stateless service calls,
    though connection pooling would be better for high load.
    """
    try:
        connection = await aio_pika.connect_robust(
            host=settings.RABBITMQ_HOST,
            port=settings.RABBITMQ_PORT,
            login=settings.RABBITMQ_USER,
            password=settings.RABBITMQ_PASS
        )
        async with connection:
            channel = await connection.channel()
            # Declare queue to ensure it exists
            queue = await channel.declare_queue("audit_queue", durable=True)
            
            message_body = {
                "event_type": event_type,
                "data": data
            }
            
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(message_body, default=str).encode(), # default=str handles Decimal/UUID
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key=queue.name,
            )
    except Exception as e:
        # Audit log failure should not break the main transaction, but we must log it.
        logger.error(f"Failed to publish audit log: {e}", exc_info=True)
