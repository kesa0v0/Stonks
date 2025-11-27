from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
import redis.asyncio as async_redis

from backend.core.deps import get_current_admin_user
from backend.core.cache import get_redis
from backend.models import User

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_admin_user)]
)

class FeeUpdate(BaseModel):
    fee_rate: float = Field(..., ge=0.0, le=1.0, description="Trading fee rate (e.g., 0.001 for 0.1%)")

@router.get("/fee", response_model=dict)
async def get_trading_fee(
    redis_client: async_redis.Redis = Depends(get_redis)
):
    """
    현재 거래 수수료율을 조회합니다.
    Redis에 값이 없으면 기본값(0.001, 0.1%)을 반환합니다.
    """
    fee_rate = await redis_client.get("config:trading_fee_rate")
    if fee_rate:
        return {"fee_rate": float(fee_rate)}
    return {"fee_rate": 0.001}

@router.put("/fee", response_model=dict)
async def update_trading_fee(
    fee_update: FeeUpdate,
    redis_client: async_redis.Redis = Depends(get_redis)
):
    """
    거래 수수료율을 수정합니다.
    """
    await redis_client.set("config:trading_fee_rate", str(fee_update.fee_rate))
    return {
        "message": "Trading fee rate updated successfully",
        "fee_rate": fee_update.fee_rate
    }
