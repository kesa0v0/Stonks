import redis.asyncio as async_redis
from typing import AsyncGenerator
from backend.core.config import settings

# get_sync_redis 함수 제거, 모든 Redis 사용은 비동기로 통일

async def get_redis() -> AsyncGenerator[async_redis.Redis, None]:
    client = async_redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True
    )
    try:
        yield client
    finally:
        # aclose()는 redis-py 5.x 이상에서 권장되는 비동기 클라이언트 종료 방식
        # 기존 client.close()가 TypeError를 발생시키므로 변경
        await client.aclose()