import json

# Redis Pub/Sub 기반 이벤트 발행 (공통)
async def publish_event(redis_client, event: dict, channel: str = None):
    if channel is None:
        # 이벤트 타입에 따라 기본 채널 지정
        channel = {
            "trade_executed": "trade_events",
            "price_updated": "price_events"
        }.get(event.get("type"), "events")
    await redis_client.publish(channel, json.dumps(event))
