from decimal import Decimal
import redis.asyncio as async_redis
import logging

logger = logging.getLogger(__name__)

async def get_trading_fee_rate(redis_client: async_redis.Redis) -> Decimal:
    """거래 수수료율 조회 (비동기, 기본값 0.1%)"""
    try:
        rate = await redis_client.get("config:trading_fee_rate")
        if rate:
            if isinstance(rate, bytes):
                rate = rate.decode()
            return Decimal(str(rate))
        return Decimal("0.001")
    except Exception as e:
        logger.error(f"Failed to fetch fee rate: {e}")
        return Decimal("0.001")
