from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Security, Query
import redis.asyncio as async_redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta

from backend.core.cache import get_redis
from backend.core.database import get_db
from backend.core.deps import get_current_user_by_api_key, get_current_user_any
from backend.services.trade_service import get_current_price
from backend.models import Ticker, Candle
from backend.schemas.market import TickerResponse, CurrentPriceResponse
from backend.schemas.candle import CandleResponse

router = APIRouter(prefix="/market", tags=["market"])

@router.get("/tickers", response_model=List[TickerResponse])
async def get_tickers(
    db: AsyncSession = Depends(get_db)
):
    """
    상장된 모든 활성 종목 리스트를 조회합니다.
    """
    result = await db.execute(select(Ticker).where(Ticker.is_active == True))
    tickers = result.scalars().all()
    return tickers

@router.get("/candles/{ticker_id}", response_model=List[CandleResponse])
async def get_candles(
    ticker_id: str,
    interval: str = Query("1m", pattern="^(1m|1d)$"), # 1m 또는 1d 만 허용
    limit: int = Query(100, le=500), 
    db: AsyncSession = Depends(get_db)
):
    """
    특정 종목의 과거 차트 데이터(분봉/일봉)를 조회합니다.
    - interval: "1m" (분봉) 또는 "1d" (일봉)
    """
    # 최신순으로 limit개 조회 후 시간 오름차순 정렬하여 반환
    stmt = (
        select(Candle)
        .where(Candle.ticker_id == ticker_id, Candle.interval == interval)
        .order_by(Candle.timestamp.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    candles = result.scalars().all()
    
    # 차트 라이브러리는 보통 시간 오름차순(과거->최신)을 선호하므로 뒤집어서 반환
    return list(reversed(candles))

@router.get("/price/{ticker_id}", response_model=CurrentPriceResponse, dependencies=[Security(get_current_user_by_api_key)])
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
    
    return CurrentPriceResponse(ticker_id=ticker_id, price=float(price_decimal))

@router.get("/price-any/{ticker_id}", response_model=CurrentPriceResponse)
async def get_ticker_current_price_multi_auth(
    ticker_id: str,
    redis_client: async_redis.Redis = Depends(get_redis),
    _user=Depends(get_current_user_any)
):
    price_decimal = await get_current_price(redis_client, ticker_id)
    if price_decimal is None:
        return CurrentPriceResponse(ticker_id=ticker_id, price=None, message=f"Price data not available for {ticker_id}")
    return CurrentPriceResponse(ticker_id=ticker_id, price=float(price_decimal))
