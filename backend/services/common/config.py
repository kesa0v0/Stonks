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

async def get_whale_threshold_krw(redis_client: async_redis.Redis) -> int:
    """고래 알림 임계치(KRW) 조회 (Redis → 기본값)"""
    try:
        val = await redis_client.get(constants.REDIS_KEY_WHALE_THRESHOLD_KRW)
        if val:
            if isinstance(val, bytes):
                val = val.decode()
            return int(val)
        return int(constants.DEFAULT_WHALE_THRESHOLD_KRW)
    except Exception as e:
        logger.error(f"Failed to fetch whale threshold: {e}")
        return int(constants.DEFAULT_WHALE_THRESHOLD_KRW)

def _safe_format(template: str, data: dict) -> str:
    class _MissingDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"
    try:
        return template.format_map(_MissingDict(**{k: v for k, v in data.items()}))
    except Exception:
        return template

async def get_message_template(redis_client: async_redis.Redis, key: str) -> str:
    """템플릿을 Redis에서 조회, 없으면 기본값 반환"""
    if key not in constants.TEMPLATE_KEYS:
        raise KeyError("Unknown template key")
    try:
        val = await redis_client.get(constants.REDIS_PREFIX_TEMPLATE + key)
        if val:
            if isinstance(val, bytes):
                val = val.decode()
            return str(val)
    except Exception as e:
        logger.error(f"Failed to fetch template {key}: {e}")
    return constants.DEFAULT_TEMPLATES.get(key, "")

async def set_message_template(redis_client: async_redis.Redis, key: str, content: str) -> None:
    if key not in constants.TEMPLATE_KEYS:
        raise KeyError("Unknown template key")
    await redis_client.set(constants.REDIS_PREFIX_TEMPLATE + key, content)

async def list_all_templates(redis_client: async_redis.Redis) -> dict:
    """모든 템플릿을 {key: content} 형태로 반환 (저장→없으면 기본값)"""
    result = {}
    for key in constants.TEMPLATE_KEYS:
        result[key] = await get_message_template(redis_client, key)
    return result
