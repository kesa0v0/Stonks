from datetime import datetime, time
import time as time_lib
import json
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc, asc
from sqlalchemy.orm import aliased
import redis.asyncio as async_redis
import aiohttp
from decimal import Decimal # Added Decimal import

from backend.models import Ticker, Candle, Order, User
from backend.models.asset import MarketType
from backend.core.enums import OrderStatus, OrderType, OrderSide
from backend.schemas.market import MarketState, OrderBookEntry, OrderBookResponse, MarketStatusResponse, MoverResponse, TickerResponse
import json
import redis.asyncio as async_redis
from backend.services.common.price import get_current_price

def get_market_status_by_type(market_type: str, now: datetime) -> MarketState:
    """
    현재 시간 기준 시장 상태 판별 (단순화된 로직)
    """
    if market_type == "CRYPTO":
        return MarketState.OPEN # 24/7
    
    if market_type == "HUMAN":
        return MarketState.OPEN # 24/7 for Human ETFs

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

async def get_active_tickers(db: AsyncSession, redis_client: async_redis.Redis) -> List[TickerResponse]:
    """
    상장된 모든 활성 종목 리스트를 조회합니다. (현재가, 변동률, 일일 거래량 포함)
    """
    # Latest 1d candle (for Previous Close)
    prev_stmt = (
        select(Candle)
        .where(Candle.interval == '1d')
        .distinct(Candle.ticker_id)
        .order_by(Candle.ticker_id, Candle.timestamp.desc())
        .subquery()
    )
    prev = aliased(Candle, prev_stmt)
    
    # Daily Volume (from 00:00 UTC today)
    utc_tz = ZoneInfo("UTC")
    today_start_utc = datetime.now(utc_tz).replace(hour=0, minute=0, second=0, microsecond=0)
    
    daily_volume_stmt = (
        select(
            Candle.ticker_id,
            func.sum(Candle.volume).label("daily_volume")
        )
        .where(
            Candle.interval == '1m',
            Candle.timestamp >= today_start_utc
        )
        .group_by(Candle.ticker_id)
        .subquery()
    )
    daily_volume = aliased(daily_volume_stmt, name="daily_volume")


    stmt = (
        select(
            Ticker,
            prev.close.label("prev_close"),
            daily_volume.c.daily_volume
        )
        .outerjoin(prev, Ticker.id == prev.ticker_id)
        .outerjoin(daily_volume, Ticker.id == daily_volume.c.ticker_id)
        .where(Ticker.is_active == True)
    )

    result = await db.execute(stmt)
    rows = result.all()

    # Fetch all user dividend rates for mapping
    user_stmt = select(User.id, User.dividend_rate).where(User.is_active == True)
    user_result = await db.execute(user_stmt)
    # Map str(user_id) -> dividend_rate (multiply by 100 for percentage display if needed, but standard is rate. Schema expects DecimalStr)
    # User.dividend_rate is e.g. 0.5000 for 50%. Let's return "50.00" or "0.50".
    # The request says "50%, 90%". So let's format as percentage string.
    user_dividend_map = {str(uid): float(rate) * 100 for uid, rate in user_result.all()}

    tickers = []
    # Batch fetch realtime prices from Redis
    ids: List[str] = [row[0].id for row in rows]
    keys = [f"price:{tid}" for tid in ids]
    try:
        raw_values = await redis_client.mget(keys)
    except Exception:
        raw_values = [None] * len(keys)

    # Build map id -> price (float)
    price_map: Dict[str, Optional[float]] = {}
    for tid, raw in zip(ids, raw_values):
        if not raw:
            price_map[tid] = None
            continue
        try:
            data = json.loads(raw)
            price = Decimal(data.get("price")) if data and data.get("price") is not None else None
            price_map[tid] = price
        except Exception:
            price_map[tid] = None

    # Build response using Redis price and prev_close for change percent
    for row in rows:
        ticker_obj: Ticker = row[0]
        prev_close = row[1]
        d_volume = row[2]

        t_res = TickerResponse.model_validate(ticker_obj)

        rt_price = price_map.get(ticker_obj.id)
        if rt_price is not None:
            t_res.current_price = str(rt_price)

        t_res.volume = str(d_volume) if d_volume is not None else '0'

        try:
            if rt_price is not None and prev_close not in (None, Decimal(0)): # Check against Decimal 0
                change_pct = (rt_price - prev_close) / prev_close * Decimal("100")
                t_res.change_percent = f"{change_pct:.2f}"
        except Exception:
            pass
        
        # Populate Dividend Rate for Human ETF
        if ticker_obj.market_type == MarketType.HUMAN and ticker_obj.id.startswith("HUMAN-"):
            try:
                # Extract User UUID from Ticker ID "HUMAN-{uuid}"
                user_id_str = ticker_obj.id.replace("HUMAN-", "")
                if user_id_str in user_dividend_map:
                    t_res.dividend_rate = f"{user_dividend_map[user_id_str]:.2f}" # "50.00"
            except Exception:
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

async def get_orderbook_data(db: AsyncSession, ticker_id: str, redis_client: async_redis.Redis | None = None) -> OrderBookResponse:
    """
    특정 종목의 내부 호가창(Orderbook)을 조회합니다.
    """
    # 1) 우선 Redis 캐시(실시간 거래소 호가) 조회
    if redis_client is not None:
        try:
            raw = await redis_client.get(f"orderbook:{ticker_id}")
            if raw:
                obj = json.loads(raw)
                asks = [
                    OrderBookEntry(price=Decimal(x.get("price", "0")), quantity=Decimal(x.get("quantity", "0")))
                    for x in obj.get("asks", [])
                ]
                bids = [
                    OrderBookEntry(price=Decimal(x.get("price", "0")), quantity=Decimal(x.get("quantity", "0")))
                    for x in obj.get("bids", [])
                ]
                # Timestamp retrieval
                ts = float(obj.get("timestamp", time_lib.time()))
                return OrderBookResponse(ticker_id=ticker_id, bids=bids, asks=asks, timestamp=ts)
        except Exception:
            # Redis/JSON 문제 시 조용히 DB fallback
            pass

    # 2) Fallback: 내부 지정가 주문 집계로 호가 구성
    # 매수/매도 별로 그룹화하여 집계
    # PENDING LIMIT 주문의 경우, target_price가 호가입니다. (price는 체결가)
    stmt = (
        select(
            Order.side,
            Order.target_price.label("price"), 
            func.sum(Order.unfilled_quantity).label("quantity")
        )
        .where(
            Order.ticker_id == ticker_id,
            Order.status == OrderStatus.PENDING,
            Order.type == OrderType.LIMIT
        )
        .group_by(Order.side, Order.target_price)
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    bids = []
    asks = []
    
    for side, price, quantity in rows:
        p_val = price if price is not None else Decimal("0.0")
        q_val = quantity if quantity is not None else Decimal("0.0")
        
        entry = OrderBookEntry(price=p_val, quantity=q_val)
        if side == OrderSide.BUY:
            bids.append(entry)
        else:
            asks.append(entry)
            
    # 정렬: 매수(Bids)는 비싼 순(내림차순), 매도(Asks)는 싼 순(오름차순)
    bids.sort(key=lambda x: x.price, reverse=True)
    asks.sort(key=lambda x: x.price)
    
    return OrderBookResponse(ticker_id=ticker_id, bids=bids, asks=asks, timestamp=time_lib.time())

async def get_current_price_info(redis_client: async_redis.Redis, ticker_id: str) -> Optional[float]:
    price_decimal = await get_current_price(redis_client, ticker_id)
    if price_decimal is None:
        return None
    return price_decimal

async def publish_current_orderbook_snapshot(db: AsyncSession, redis_client: async_redis.Redis, ticker_id: str):
    """
    현재 DB에 있는 지정가 미체결 주문을 집계하여 호가창 스냅샷을 구성하고 Redis에 발행합니다.
    주로 Human ETF의 호가창 업데이트에 사용됩니다.
    """
    # 내부 지정가 주문 집계로 호가 구성 (get_orderbook_data의 Fallback 로직 재활용)
    stmt = (
        select(
            Order.side,
            Order.target_price.label("price"), 
            func.sum(Order.unfilled_quantity).label("quantity")
        )
        .where(
            Order.ticker_id == ticker_id,
            Order.status == OrderStatus.PENDING,
            Order.type == OrderType.LIMIT
        )
        .group_by(Order.side, Order.target_price)
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    bids = []
    asks = []
    
    for side, price, quantity in rows:
        p_val = price if price is not None else Decimal("0.0")
        q_val = quantity if quantity is not None else Decimal("0.0")
        
        entry = OrderBookEntry(price=p_val, quantity=q_val) # Use DecimalStr
        if side == OrderSide.BUY:
            bids.append(entry)
        else:
            asks.append(entry)
            
    # 정렬: 매수(Bids)는 비싼 순(내림차순), 매도(Asks)는 싼 순(오름차순)
    bids.sort(key=lambda x: Decimal(x.price), reverse=True)
    asks.sort(key=lambda x: Decimal(x.price))
    
    orderbook_snapshot = OrderBookResponse(ticker_id=ticker_id, bids=bids, asks=asks, timestamp=time_lib.time())

    # Redis 발행
    await redis_client.publish("orderbook_updates", orderbook_snapshot.model_dump_json())

async def get_top_movers(db: AsyncSession, type: str, limit: int) -> List[MoverResponse]:
    """
    등락률 상위(Gainers) 또는 하위(Losers) 종목 조회 (일일 거래량 포함)
    """
    # 1. Latest 1m candles (for Current Price)
    curr_stmt = (
        select(Candle)
        .where(Candle.interval == '1m')
        .distinct(Candle.ticker_id)
        .order_by(Candle.ticker_id, Candle.timestamp.desc())
        .subquery()
    )
    curr = aliased(Candle, curr_stmt)

    # 2. Latest 1d candles (for Previous Close)
    prev_stmt = (
        select(Candle)
        .where(Candle.interval == '1d')
        .distinct(Candle.ticker_id)
        .order_by(Candle.ticker_id, Candle.timestamp.desc())
        .subquery()
    )
    prev = aliased(Candle, prev_stmt)
    
    # 3. Daily Volume (from 00:00 UTC today)
    utc_tz = ZoneInfo("UTC")
    today_start_utc = datetime.now(utc_tz).replace(hour=0, minute=0, second=0, microsecond=0)
    
    daily_volume_stmt = (
        select(
            Candle.ticker_id,
            func.sum(Candle.volume).label("daily_volume")
        )
        .where(
            Candle.interval == '1m',
            Candle.timestamp >= today_start_utc
        )
        .group_by(Candle.ticker_id)
        .subquery()
    )
    daily_volume = aliased(daily_volume_stmt, name="daily_volume")

    # 4. Join & Calculate Change %
    change_expr = (curr.close - prev.close) / prev.close * 100

    stmt = (
        select(
            Ticker, 
            curr, 
            change_expr.label("change_percent"),
            daily_volume.c.daily_volume
        )
        .join(curr, Ticker.id == curr.ticker_id)
        .join(prev, Ticker.id == prev.ticker_id)
        .outerjoin(daily_volume, Ticker.id == daily_volume.c.ticker_id)
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
        ticker, candle_1m, change_pct, d_volume = row
        daily_vol = d_volume if d_volume is not None else 0
        
        movers.append(MoverResponse(
            ticker=TickerResponse.model_validate(ticker),
            price=str(candle_1m.close),
            change_percent=f"{change_pct:.2f}",
            volume=str(daily_vol),
            value=str(candle_1m.close * daily_vol)
        ))
    return movers

async def get_trending_tickers(db: AsyncSession, limit: int) -> List[MoverResponse]:
    """
    거래대금(Value) 상위 종목 조회 (일일 기준)
    """
    # Latest 1m candle (for Current Price)
    curr_stmt = (
        select(Candle)
        .where(Candle.interval == '1m')
        .distinct(Candle.ticker_id)
        .order_by(Candle.ticker_id, Candle.timestamp.desc())
        .subquery()
    )
    curr = aliased(Candle, curr_stmt)
    
    # Daily Volume (from 00:00 UTC today)
    utc_tz = ZoneInfo("UTC")
    today_start_utc = datetime.now(utc_tz).replace(hour=0, minute=0, second=0, microsecond=0)
    
    daily_volume_stmt = (
        select(
            Candle.ticker_id,
            func.sum(Candle.volume).label("daily_volume")
        )
        .where(
            Candle.interval == '1m',
            Candle.timestamp >= today_start_utc
        )
        .group_by(Candle.ticker_id)
        .subquery()
    )
    daily_volume = aliased(daily_volume_stmt, name="daily_volume")

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
    
    # Calculate daily trade value = current_price * daily_volume
    daily_value_expr = curr.close * daily_volume.c.daily_volume

    stmt = (
        select(
            Ticker, 
            curr, 
            change_expr.label("change_percent"), 
            daily_volume.c.daily_volume,
            daily_value_expr.label("daily_trade_value")
        )
        .join(curr, Ticker.id == curr.ticker_id)
        .join(daily_volume, Ticker.id == daily_volume.c.ticker_id) # Must have volume today to be trending
        .outerjoin(prev, Ticker.id == prev.ticker_id) # Use outerjoin in case 1d is missing
        .where(Ticker.is_active == True)
        .order_by(desc("daily_trade_value"))
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    trends = []
    for row in rows:
        ticker, candle_1m, change_pct, d_volume, d_value = row
        change_str = f"{change_pct:.2f}" if change_pct is not None else "0.00"
        
        trends.append(MoverResponse(
            ticker=TickerResponse.model_validate(ticker),
            price=str(candle_1m.close),
            change_percent=change_str,
            volume=str(d_volume) if d_volume is not None else '0',
            value=str(d_value) if d_value is not None else '0'
        ))
    return trends

# --- FX rate ---
FX_CACHE_PREFIX = "fx:rate:"
FX_TTL_SECONDS = 600

async def get_fx_rate(redis_client: async_redis.Redis, base: str, quote: str) -> float:
    """Fetch FX rate from free source with Redis cache fallback.
    Uses exchangerate.host latest endpoint.
    """
    key = f"{FX_CACHE_PREFIX}{base}:{quote}"
    # Try cache
    try:
        cached = await redis_client.get(key)
        if cached:
            return float(cached)
    except Exception:
        pass

    url = f"https://api.exchangerate.host/latest?base={base}&symbols={quote}"
    rate: Optional[float] = None
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if isinstance(data, dict) and "rates" in data and quote in data["rates"]:
                    r = data["rates"][quote]
                    if isinstance(r, (int, float)):
                        rate = float(r)
    except Exception:
        rate = None

    if rate is None or not (rate > 0):
        rate = 1300.0

    try:
        await redis_client.set(key, str(rate), ex=FX_TTL_SECONDS)
    except Exception:
        pass

    return rate
