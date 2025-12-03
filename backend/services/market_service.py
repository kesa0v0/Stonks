from datetime import datetime, time
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc, asc
from sqlalchemy.orm import aliased
import redis.asyncio as async_redis

from backend.models import Ticker, Candle, Order
from backend.core.enums import OrderStatus, OrderType, OrderSide
from backend.schemas.market import MarketState, OrderBookEntry, OrderBookResponse, MarketStatusResponse, MoverResponse, TickerResponse
from backend.services.common.price import get_current_price

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

async def get_all_market_status() -> MarketStatusResponse:
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

async def get_active_tickers(db: AsyncSession) -> List[TickerResponse]:
    """
    상장된 모든 활성 종목 리스트를 조회합니다. (현재가, 변동률 포함)
    """
    # Latest 1m candle (Current Price & Volume)
    curr_stmt = (
        select(Candle)
        .where(Candle.interval == '1m')
        .distinct(Candle.ticker_id)
        .order_by(Candle.ticker_id, Candle.timestamp.desc())
        .subquery()
    )
    curr = aliased(Candle, curr_stmt)

    # Latest 1d candle (Previous Close)
    prev_stmt = (
        select(Candle)
        .where(Candle.interval == '1d')
        .distinct(Candle.ticker_id)
        .order_by(Candle.ticker_id, Candle.timestamp.desc())
        .subquery()
    )
    prev = aliased(Candle, prev_stmt)

    # Calculate Change %
    change_expr = (curr.close - prev.close) / prev.close * 100

    stmt = (
        select(Ticker, curr, change_expr.label("change_percent"))
        .outerjoin(curr, Ticker.id == curr.ticker_id)
        .outerjoin(prev, Ticker.id == prev.ticker_id)
        .where(Ticker.is_active == True)
    )

    result = await db.execute(stmt)
    rows = result.all()

    tickers = []
    for row in rows:
        ticker_obj, candle_1m, change_pct = row
        
        # Build response
        t_res = TickerResponse.model_validate(ticker_obj)
        
        if candle_1m:
            t_res.current_price = str(candle_1m.close)
            t_res.volume = str(candle_1m.volume)
            
        if change_pct is not None:
            t_res.change_percent = f"{change_pct:.2f}"
        else:
             # If no data, 0.00 or None. Let's default to 0.00 if price exists? 
             # Or None. None is safer to indicate "no data".
             pass

        tickers.append(t_res)
        
    return tickers

async def search_tickers_by_name(db: AsyncSession, query: str, limit: int) -> List[TickerResponse]:
    """
    종목 이름 또는 심볼로 종목을 검색합니다. (현재가 포함)
    """
    search_pattern = f"%{query}%" 
    
    # Reuse similar logic for price data
    curr_stmt = (
        select(Candle)
        .where(Candle.interval == '1m')
        .distinct(Candle.ticker_id)
        .order_by(Candle.ticker_id, Candle.timestamp.desc())
        .subquery()
    )
    curr = aliased(Candle, curr_stmt)

    prev_stmt = (
        select(Candle)
        .where(Candle.interval == '1d')
        .distinct(Candle.ticker_id)
        .order_by(Candle.ticker_id, Candle.timestamp.desc())
        .subquery()
    )
    prev = aliased(Candle, prev_stmt)

    change_expr = (curr.close - prev.close) / prev.close * 100
    
    stmt = (
        select(Ticker, curr, change_expr.label("change_percent"))
        .outerjoin(curr, Ticker.id == curr.ticker_id)
        .outerjoin(prev, Ticker.id == prev.ticker_id)
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
    rows = result.all()

    tickers = []
    for row in rows:
        ticker_obj, candle_1m, change_pct = row
        t_res = TickerResponse.model_validate(ticker_obj)
        
        if candle_1m:
            t_res.current_price = str(candle_1m.close)
            t_res.volume = str(candle_1m.volume)
        
        if change_pct is not None:
            t_res.change_percent = f"{change_pct:.2f}"
            
        tickers.append(t_res)
        
    return tickers

async def get_candle_history(db: AsyncSession, ticker_id: str, interval: str, limit: int, before: Optional[datetime] = None, after: Optional[datetime] = None) -> List[Candle]:
    """
    특정 종목의 과거 차트 데이터(분봉/일봉)를 조회합니다.
    before: 이 시간 이전의 데이터만 조회 (pagination)
    after: 이 시간 이후의 데이터만 조회 (range filtering)
    """
    stmt = (
        select(Candle)
        .where(Candle.ticker_id == ticker_id, Candle.interval == interval)
    )
    
    if before:
        stmt = stmt.where(Candle.timestamp < before)
    
    if after:
        stmt = stmt.where(Candle.timestamp >= after)
        
    stmt = (
        stmt
        .order_by(Candle.timestamp.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    candles = result.scalars().all()
    
    # 차트 라이브러리는 보통 시간 오름차순(과거->최신)을 선호하므로 뒤집어서 반환
    return list(reversed(candles))

async def get_orderbook_data(db: AsyncSession, ticker_id: str) -> OrderBookResponse:
    """
    특정 종목의 내부 호가창(Orderbook)을 조회합니다.
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

async def get_current_price_info(redis_client: async_redis.Redis, ticker_id: str) -> Optional[float]:
    price_decimal = await get_current_price(redis_client, ticker_id)
    if price_decimal is None:
        return None
    return float(price_decimal)

async def get_top_movers(db: AsyncSession, type: str, limit: int) -> List[MoverResponse]:
    """
    등락률 상위(Gainers) 또는 하위(Losers) 종목 조회
    """
    # 1. Latest 1m candles (Current Price)
    # Postgres specific DISTINCT ON
    curr_stmt = (
        select(Candle)
        .where(Candle.interval == '1m')
        .distinct(Candle.ticker_id)
        .order_by(Candle.ticker_id, Candle.timestamp.desc())
        .subquery()
    )
    curr = aliased(Candle, curr_stmt)

    # 2. Latest 1d candles (Previous Close)
    prev_stmt = (
        select(Candle)
        .where(Candle.interval == '1d')
        .distinct(Candle.ticker_id)
        .order_by(Candle.ticker_id, Candle.timestamp.desc())
        .subquery()
    )
    prev = aliased(Candle, prev_stmt)

    # 3. Join & Calculate
    # change_pct = (curr.close - prev.close) / prev.close * 100
    change_expr = (curr.close - prev.close) / prev.close * 100

    stmt = (
        select(Ticker, curr, change_expr.label("change_percent"))
        .join(curr, Ticker.id == curr.ticker_id)
        .join(prev, Ticker.id == prev.ticker_id)
        .where(Ticker.is_active == True)
    )

    if type == "gainers":
        stmt = stmt.order_by(desc("change_percent"))
    else:
        stmt = stmt.order_by(asc("change_percent"))
    
    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    rows = result.all()

    movers = []
    for row in rows:
        ticker, candle_1m, change_pct = row
        movers.append(MoverResponse(
            ticker=TickerResponse.model_validate(ticker),
            price=str(candle_1m.close),
            change_percent=f"{change_pct:.2f}",
            volume=str(candle_1m.volume),
            value=str(candle_1m.close * candle_1m.volume)
        ))
    return movers

async def get_trending_tickers(db: AsyncSession, limit: int) -> List[MoverResponse]:
    """
    거래대금(Value) 급증 종목 조회 (최근 1분봉 기준)
    """
    # Latest 1m candle
    curr_stmt = (
        select(Candle)
        .where(Candle.interval == '1m')
        .distinct(Candle.ticker_id)
        .order_by(Candle.ticker_id, Candle.timestamp.desc())
        .subquery()
    )
    curr = aliased(Candle, curr_stmt)
    
    # Calculate Value = close * volume
    value_expr = curr.close * curr.volume
    
    # We also need prev_close for change_percent
    prev_stmt = (
        select(Candle)
        .where(Candle.interval == '1d')
        .distinct(Candle.ticker_id)
        .order_by(Candle.ticker_id, Candle.timestamp.desc())
        .subquery()
    )
    prev = aliased(Candle, prev_stmt)
    
    change_expr = (curr.close - prev.close) / prev.close * 100

    stmt = (
        select(Ticker, curr, change_expr.label("change_percent"), value_expr.label("trade_value"))
        .join(curr, Ticker.id == curr.ticker_id)
        .outerjoin(prev, Ticker.id == prev.ticker_id) # Use outerjoin in case 1d is missing
        .where(Ticker.is_active == True)
        .order_by(desc("trade_value"))
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    trends = []
    for row in rows:
        ticker, candle_1m, change_pct, trade_val = row
        change_str = f"{change_pct:.2f}" if change_pct is not None else "0.00"
        
        trends.append(MoverResponse(
            ticker=TickerResponse.model_validate(ticker),
            price=str(candle_1m.close),
            change_percent=change_str,
            volume=str(candle_1m.volume),
            value=str(trade_val)
        ))
    return trends
