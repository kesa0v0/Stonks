from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import redis.asyncio as async_redis
from backend.core.cache import get_redis
from backend.services.trade_service import get_current_price

router = APIRouter(prefix="/market-data", tags=["market-data"])

class CurrentPriceResponse(BaseModel):
    ticker_id: str
    price: Optional[float] = None
    message: Optional[str] = None

@router.get("/price/{ticker_id}", response_model=CurrentPriceResponse)
async def get_ticker_current_price(
    ticker_id: str,
    redis_client: async_redis.Redis = Depends(get_redis)
):
    """
    특정 티커의 현재 시장 가격을 조회합니다.
    """
    # trade_service의 get_current_price가 async 함수이고 redis_client를 인자로 받음
    price_decimal = await get_current_price(redis_client, ticker_id)
    
    if price_decimal is None:
        return CurrentPriceResponse(
            ticker_id=ticker_id,
            price=None,
            message=f"Price data not available for {ticker_id}"
        )
    
    return CurrentPriceResponse(
        ticker_id=ticker_id,
        price=float(price_decimal)
    )
