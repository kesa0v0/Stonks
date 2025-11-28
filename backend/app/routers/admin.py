from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
import redis.asyncio as async_redis
import json


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

class PriceUpdate(BaseModel):
    ticker_id: str
    price: float

@router.post("/price")
async def set_test_price_admin(update: PriceUpdate, redis_client: async_redis.Redis = Depends(get_redis)):
    """
    [관리자용] 특정 코인의 가격을 강제로 변경하고 이벤트를 발생시킵니다.
    이 API를 호출하면 limit_matcher가 즉시 반응하여 지정가 주문을 체결합니다.
    """
    price_data = {
        "ticker_id": update.ticker_id,
        "price": update.price,
        "timestamp": "ADMIN_MANUAL_UPDATE"
    }
    await redis_client.set(f"price:{update.ticker_id}", json.dumps(price_data))
    await redis_client.publish("market_updates", json.dumps(price_data))
    return {"status": "ok", "message": f"Price of {update.ticker_id} set to {update.price}"}