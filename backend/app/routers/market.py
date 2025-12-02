from typing import List
from fastapi import APIRouter, Depends, Security, Query
from backend.core.rate_limit_config import get_rate_limiter
import redis.asyncio as async_redis
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import get_redis
from backend.core.database import get_db
from backend.core.deps import get_current_user_by_api_key, get_current_user_any
from backend.schemas.market import TickerResponse, CurrentPriceResponse, MarketStatusResponse, OrderBookResponse, MoverResponse
from backend.schemas.candle import CandleResponse
from backend.services.market_service import (
    get_all_market_status,
    get_active_tickers,
    search_tickers_by_name,
    get_candle_history,
    get_orderbook_data,
    get_current_price_info,
    get_top_movers,
    get_trending_tickers
)

router = APIRouter(prefix="/market", tags=["market"])

@router.get("/status", response_model=MarketStatusResponse, dependencies=[Depends(get_rate_limiter("/market/status"))])
async def get_market_status():
    """
    현재 각 시장(KRX, US, CRYPTO)의 운영 상태를 반환합니다.
    """
    return await get_all_market_status()

@router.get("/tickers", response_model=List[TickerResponse], dependencies=[Depends(get_rate_limiter("/market/tickers"))])
async def get_tickers(
    db: AsyncSession = Depends(get_db)
):
    """
    상장된 모든 활성 종목 리스트를 조회합니다.
    """
    return await get_active_tickers(db)

@router.get("/search", response_model=List[TickerResponse], dependencies=[Depends(get_rate_limiter("/market/search"))])
async def search_tickers(
    query: str = Query(..., min_length=1, description="종목 이름 또는 심볼 검색어"),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """
    종목 이름 또는 심볼로 종목을 검색합니다.
    """
    return await search_tickers_by_name(db, query, limit)


@router.get("/candles/{ticker_id}", response_model=List[CandleResponse], dependencies=[Depends(get_rate_limiter("/market/candles/{ticker_id}"))])
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
    return await get_candle_history(db, ticker_id, interval, limit)

@router.get("/orderbook/{ticker_id}", response_model=OrderBookResponse, dependencies=[Depends(get_rate_limiter("/market/orderbook/{ticker_id}"))])
async def get_orderbook(
    ticker_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    특정 종목의 내부 호가창(Orderbook)을 조회합니다.
    참가자들의 미체결 지정가 주문(LIMIT)을 집계하여 보여줍니다.
    """
    return await get_orderbook_data(db, ticker_id)

@router.get("/price/{ticker_id}", response_model=CurrentPriceResponse, dependencies=[Depends(get_rate_limiter("/market/price/{ticker_id}"))])
async def get_ticker_current_price(
    ticker_id: str,
    redis_client: async_redis.Redis = Depends(get_redis),
    _user=Depends(get_current_user_any)
):
    """
    특정 티커의 현재 시장 가격을 조회합니다.
    인증: Bearer Token (로그인) 또는 X-API-Key 모두 지원.
    """
    price = await get_current_price_info(redis_client, ticker_id)
    
    if price is None:
        return CurrentPriceResponse(
            ticker_id=ticker_id,
            price=None,
            message=f"Price data not available for {ticker_id}"
        )
    
    return CurrentPriceResponse(ticker_id=ticker_id, price=price)

@router.get("/movers", response_model=List[MoverResponse], dependencies=[Depends(get_rate_limiter("/market/movers"))])
async def get_movers_endpoint(
    type: str = Query(..., pattern="^(gainers|losers)$"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """
    오늘의 등락률 상위(gainers) / 하위(losers) 종목을 조회합니다.
    """
    return await get_top_movers(db, type, limit)

@router.get("/trending", response_model=List[MoverResponse], dependencies=[Depends(get_rate_limiter("/market/trending"))])
async def get_trending_endpoint(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """
    현재 거래가 가장 활발한(거래대금 급증) 종목을 조회합니다.
    """
    return await get_trending_tickers(db, limit)
