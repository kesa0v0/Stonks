import json
import asyncio

# RabbitMQ 예시 (aio_pika)
# import aio_pika
# async def publish_event(event: dict):
#     connection = await aio_pika.connect_robust("amqp://guest:guest@localhost/")
#     channel = await connection.channel()
#     exchange = await channel.declare_exchange("trade_events", aio_pika.ExchangeType.FANOUT)
#     await exchange.publish(
#         aio_pika.Message(body=json.dumps(event).encode()),
#         routing_key=""
#     )
#     await connection.close()

# Redis 예시 (aioredis)
async def publish_event(redis_client, event: dict):
    channel = "trade_events"
    await redis_client.publish(channel, json.dumps(event))
