# fastapi-limiter 설정 및 Redis 연결
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
import redis.asyncio as redis
from backend.core.config import settings

async def init_rate_limiter():
    redis_client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True
    )
    await FastAPILimiter.init(redis_client)
