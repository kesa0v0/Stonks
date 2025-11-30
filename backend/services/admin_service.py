import json
import redis.asyncio as async_redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core import constants
from backend.core.exceptions import TickerAlreadyExistsError, TickerNotFoundError
from backend.models import Ticker
from backend.schemas.market import TickerCreate, TickerUpdate, TickerResponse
from backend.schemas.admin import FeeUpdate, PriceUpdate

from backend.services.common.config import get_trading_fee_rate

async def get_current_trading_fee(redis_client: async_redis.Redis) -> dict:
    """
    현재 거래 수수료율을 조회합니다.
    """
    fee_rate = await get_trading_fee_rate(redis_client)
    return {"fee_rate": float(fee_rate)}

async def update_trading_fee_config(redis_client: async_redis.Redis, fee_update: FeeUpdate) -> dict:
    """
    거래 수수료율을 수정합니다.
    """
    await redis_client.set(constants.REDIS_KEY_TRADING_FEE_RATE, str(fee_update.fee_rate))
    return {
        "message": "Trading fee rate updated successfully",
        "fee_rate": fee_update.fee_rate
    }

async def set_admin_test_price(redis_client: async_redis.Redis, update: PriceUpdate):
    """
    [관리자용] 특정 코인의 가격을 강제로 변경하고 이벤트를 발생시킵니다.
    """
    price_data = {
        "ticker_id": update.ticker_id,
        "price": update.price,
        "timestamp": "ADMIN_MANUAL_UPDATE"
    }
    await redis_client.set(f"{constants.REDIS_PREFIX_PRICE}{update.ticker_id}", json.dumps(price_data))
    await redis_client.publish(constants.REDIS_CHANNEL_MARKET_UPDATES, json.dumps(price_data))
    return {"status": "ok", "message": f"Price of {update.ticker_id} set to {update.price}"}

async def create_new_ticker(db: AsyncSession, ticker_in: TickerCreate) -> Ticker:
    """
    새로운 종목을 추가합니다.
    """
    existing = await db.execute(select(Ticker).where(Ticker.id == ticker_in.id))
    if existing.scalars().first():
        raise TickerAlreadyExistsError(f"Ticker ID {ticker_in.id} already exists.")

    ticker = Ticker(
        id=ticker_in.id, # 입력받은 id 사용
        **ticker_in.model_dump(exclude={"id"})
    )
    db.add(ticker)
    await db.commit()
    await db.refresh(ticker)
    return ticker

async def update_existing_ticker(db: AsyncSession, ticker_id: str, ticker_in: TickerUpdate) -> Ticker:
    """
    종목 정보를 수정합니다.
    """
    result = await db.execute(select(Ticker).where(Ticker.id == ticker_id))
    ticker = result.scalars().first()
    
    if not ticker:
        raise TickerNotFoundError()
    
    update_data = ticker_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(ticker, key, value)
        
    await db.commit()
    await db.refresh(ticker)
    return ticker

async def delete_existing_ticker(db: AsyncSession, ticker_id: str):
    """
    종목을 삭제합니다.
    """
    result = await db.execute(select(Ticker).where(Ticker.id == ticker_id))
    ticker = result.scalars().first()
    
    if not ticker:
        raise TickerNotFoundError()
        
    await db.delete(ticker)
    await db.commit()
    
    return {"message": f"Ticker {ticker_id} deleted successfully"}
