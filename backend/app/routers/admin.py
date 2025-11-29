from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
import redis.asyncio as async_redis
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from backend.core.deps import get_current_admin_user
from backend.core.cache import get_redis
from backend.core.database import get_db
from backend.models import User, Ticker, MarketType, Currency
from backend.schemas.market import TickerCreate, TickerUpdate, TickerResponse

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

# --- Ticker Management ---

@router.post("/tickers", response_model=TickerResponse)
async def create_ticker(
    ticker_in: TickerCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    새로운 종목을 추가합니다. ID는 `id` 필드를 통해 직접 지정합니다.
    """
    # 중복 체크
    existing = await db.execute(select(Ticker).where(Ticker.id == ticker_in.id))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail=f"Ticker ID {ticker_in.id} already exists.")

    ticker = Ticker(
        id=ticker_in.id, # 입력받은 id 사용
        **ticker_in.model_dump(exclude={"id"}) # id는 이미 위에서 사용했으므로 제외
    )
    db.add(ticker)
    await db.commit()
    await db.refresh(ticker)
    return ticker

@router.put("/tickers/{ticker_id}", response_model=TickerResponse)
async def update_ticker(
    ticker_id: str,
    ticker_in: TickerUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    종목 정보를 수정합니다.
    """
    result = await db.execute(select(Ticker).where(Ticker.id == ticker_id))
    ticker = result.scalars().first()
    
    if not ticker:
        raise HTTPException(status_code=404, detail="Ticker not found")
    
    update_data = ticker_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(ticker, key, value)
        
    await db.commit()
    await db.refresh(ticker)
    return ticker

@router.delete("/tickers/{ticker_id}")
async def delete_ticker(
    ticker_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    종목을 삭제합니다. (주의: 연관 데이터가 있으면 에러 발생 가능)
    """
    result = await db.execute(select(Ticker).where(Ticker.id == ticker_id))
    ticker = result.scalars().first()
    
    if not ticker:
        raise HTTPException(status_code=404, detail="Ticker not found")
        
    await db.delete(ticker)
    await db.commit()
    
    return {"message": f"Ticker {ticker_id} deleted successfully"}