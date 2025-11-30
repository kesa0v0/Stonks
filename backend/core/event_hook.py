import json

# Redis Pub/Sub 기반 이벤트 발행 유틸리티 (공통)
async def publish_event(redis_client, event: dict, channel: str):
    await redis_client.publish(channel, json.dumps(event))
