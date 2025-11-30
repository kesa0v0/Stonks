import json
from decimal import Decimal
from typing import Optional
import redis.asyncio as async_redis
import logging
from backend.core import constants

logger = logging.getLogger(__name__)

async def get_current_price(redis_client: async_redis.Redis, ticker_id: str) -> Optional[Decimal]:
    """Redis에서 현재가 조회 (비동기)"""
    try:
        data = await redis_client.get(f"{constants.REDIS_PREFIX_PRICE}{ticker_id}")
        if not data:
            return None
        price_data = json.loads(data)
        return Decimal(str(price_data['price']))
    except Exception as e:
        logger.error(f"Failed to fetch price for {ticker_id}: {e}")
        return None
