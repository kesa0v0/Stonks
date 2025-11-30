import asyncio
import json
import aioredis

async def notification_worker():
    redis = await aioredis.create_redis_pool("redis://localhost")
    channel, = await redis.subscribe("trade_events")
    print("NotificationWorker: Listening for trade events...")
    while await channel.wait_message():
        msg = await channel.get(encoding="utf-8")
        event = json.loads(msg)
        if event["type"] == "trade_executed":
            # 예시: 디스코드 메시지 전송
            print(f"[알림] {event['user_id']}님의 주문 체결: {event['side']} {event['quantity']} {event['ticker_id']} @ {event['price']}")
    redis.close()
    await redis.wait_closed()

if __name__ == "__main__":
    asyncio.run(notification_worker())
