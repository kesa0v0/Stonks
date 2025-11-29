from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Security, Query
import redis.asyncio as async_redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from datetime import datetime, timedelta, time
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo # Python 3.8 이하 호환성

from backend.core.cache import get_redis
from backend.core.database import get_db
from backend.core.deps import get_current_user_by_api_key, get_current_user_any
from backend.services.trade_service import get_current_price
from backend.models import Ticker, Candle, Order
from backend.core.enums import OrderStatus, OrderType, OrderSide
from backend.schemas.market import TickerResponse, CurrentPriceResponse, MarketStatusResponse, MarketState, OrderBookResponse, OrderBookEntry
from backend.schemas.candle import CandleResponse

router = APIRouter(prefix="/market", tags=["market"])

def get_market_status_by_type(market_type: str, now: datetime) -> MarketState:
    """
    현재 시간 기준 시장 상태 판별 (단순화된 로직)
    """
    if market_type == "CRYPTO":
        return MarketState.OPEN # 24/7
    
    if market_type == "KRX":
        # KST 기준
        kst = ZoneInfo("Asia/Seoul")
        now_kst = now.astimezone(kst)
        
        # 주말 체크 (월=0, 일=6)
        if now_kst.weekday() >= 5:
            return MarketState.CLOSED
            
        # 시간 체크 (09:00 ~ 15:30)
        current_time = now_kst.time()
        market_open = time(9, 0)
        market_close = time(15, 30)
        
        if market_open <= current_time < market_close:
            return MarketState.OPEN
        else:
            return MarketState.CLOSED
            
    if market_type == "US":
        # America/New_York 기준 (서머타임 자동 처리)
        ny_tz = ZoneInfo("America/New_York")
        now_ny = now.astimezone(ny_tz)
        
        # 주말 체크
        if now_ny.weekday() >= 5:
            return MarketState.CLOSED
            
        current_time = now_ny.time()
        
        # 프리마켓: 04:00 ~ 09:30
        # 정규장: 09:30 ~ 16:00
        # 애프터마켓: 16:00 ~ 20:00
        
        regular_open = time(9, 30)
        regular_close = time(16, 0)
        
        if regular_open <= current_time < regular_close:
            return MarketState.OPEN
        # (간단히 구현하기 위해 프리/애프터는 일단 CLOSED로 보거나 별도 처리 가능하지만, 
        # 요청사항에 따라 OPEN/CLOSED 위주로 반환. 필요시 로직 확장)
        return MarketState.CLOSED

    return MarketState.CLOSED

@router.get("/status", response_model=MarketStatusResponse)
async def get_market_status():
    """
    현재 각 시장(KRX, US, CRYPTO)의 운영 상태를 반환합니다.
    """
    now = datetime.now(ZoneInfo("UTC"))
    
    return MarketStatusResponse(
        krx=get_market_status_by_type("KRX", now),
        us=get_market_status_by_type("US", now),
        crypto=get_market_status_by_type("CRYPTO", now),
        server_time=now.isoformat()
    )

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

@router.get("/search", response_model=List[TickerResponse])
async def search_tickers(
    query: str = Query(..., min_length=1, description="종목 이름 또는 심볼 검색어"),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """
    종목 이름 또는 심볼로 종목을 검색합니다.
    """
    search_pattern = f"%{query}%" # 부분 일치 검색
    
    # SQLite 호환성을 위해 ilike 대신 lower() + like() 사용
    stmt = (
        select(Ticker)
        .where(
            Ticker.is_active == True,
            or_(
                func.lower(Ticker.name).like(func.lower(search_pattern)),
                func.lower(Ticker.symbol).like(func.lower(search_pattern))
            )
        )
        .limit(limit)
    )
    
    result = await db.execute(stmt)
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

@router.get("/orderbook/{ticker_id}", response_model=OrderBookResponse)
async def get_orderbook(
    ticker_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    특정 종목의 내부 호가창(Orderbook)을 조회합니다.
    참가자들의 미체결 지정가 주문(LIMIT)을 집계하여 보여줍니다.
    """
    # 매수/매도 별로 그룹화하여 집계
    stmt = (
        select(
            Order.side,
            Order.price, # LIMIT 주문이므로 price는 null이 아님
            func.sum(Order.unfilled_quantity).label("quantity")
        )
        .where(
            Order.ticker_id == ticker_id,
            Order.status == OrderStatus.PENDING,
            Order.type == OrderType.LIMIT
        )
        .group_by(Order.side, Order.price)
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    bids = []
    asks = []
    
    for side, price, quantity in rows:
        entry = OrderBookEntry(price=float(price), quantity=float(quantity))
        if side == OrderSide.BUY:
            bids.append(entry)
        else:
            asks.append(entry)
            
    # 정렬: 매수(Bids)는 비싼 순(내림차순), 매도(Asks)는 싼 순(오름차순)
    bids.sort(key=lambda x: x.price, reverse=True)
    asks.sort(key=lambda x: x.price)
    
    return OrderBookResponse(ticker_id=ticker_id, bids=bids, asks=asks)

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
