import redis.asyncio as async_redis
import redis
from typing import AsyncGenerator, Generator
from backend.core.config import settings

async def get_redis() -> AsyncGenerator[async_redis.Redis, None]:
    """
    Redis 클라이언트 의존성 주입 (Async)
    """
    client = async_redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True
    )
    try:
        yield client
    finally:
        await client.close()

def get_sync_redis() -> Generator[redis.Redis, None, None]:
    """
    Redis 클라이언트 의존성 주입 (Sync) - 동기 DB 세션과 함께 사용 시 권장
    """
    client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True
    )
    try:
        yield client
    finally:
        client.close()
