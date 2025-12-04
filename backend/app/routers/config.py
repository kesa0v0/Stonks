from fastapi import APIRouter, Depends
import redis.asyncio as async_redis
from backend.core.cache import get_redis
from backend.services.common.config import get_trading_fee_rate

router = APIRouter(prefix="/config", tags=["config"])

@router.get("/trading")
async def get_trading_config(redis_client: async_redis.Redis = Depends(get_redis)):
    """거래 관련 설정(수수료 등)을 반환합니다.
    현재는 단일 수수료율을 maker/taker 공통으로 제공합니다.
    """
    rate = await get_trading_fee_rate(redis_client)
    # Decimal을 문자열로 변환하여 일관성 있게 전달
    return {
        "maker_fee": str(rate),
        "taker_fee": str(rate),
    }
