from decimal import Decimal
import redis.asyncio as async_redis
import logging
from backend.core import constants

logger = logging.getLogger(__name__)

async def get_trading_fee_rate(redis_client: async_redis.Redis) -> Decimal:
    """거래 수수료율 조회 (비동기, 기본값 0.1%)"""
    try:
        rate = await redis_client.get(constants.REDIS_KEY_TRADING_FEE_RATE)
        if rate:
            if isinstance(rate, bytes):
                rate = rate.decode()
            return Decimal(str(rate))
        return Decimal(constants.DEFAULT_TRADING_FEE_RATE)
    except Exception as e:
        logger.error(f"Failed to fetch fee rate: {e}")
        return Decimal(constants.DEFAULT_TRADING_FEE_RATE)
