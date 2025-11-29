import asyncio
import ccxt.async_support as ccxt  # 비동기 버전 사용
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timezone, timedelta
import logging

# 프로젝트 모듈 임포트
from backend.core.database import AsyncSessionLocal
from backend.models import Ticker, Candle, MarketType

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("candle_collector")

async def save_candles_to_db(ohlcvs, ticker: Ticker, interval: str):
    """
    가져온 OHLCV 데이터를 DB에 저장하는 공통 함수
    """
    if not ohlcvs:
        return

    async with AsyncSessionLocal() as db:
        for ohlcv in ohlcvs:
            ts_ms = ohlcv[0]
            dt_object = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            
            open_price = ohlcv[1]
            high_price = ohlcv[2]
            low_price = ohlcv[3]
            close_price = ohlcv[4]
            volume = ohlcv[5]

            stmt = insert(Candle).values(
                ticker_id=ticker.id,
                timestamp=dt_object,
                interval=interval,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume
            ).on_conflict_do_update(
                index_elements=['ticker_id', 'timestamp', 'interval'],
                set_={
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'volume': volume
                }
            )
            await db.execute(stmt)
        
        await db.commit()

async def fetch_and_store_candles(exchange, ticker: Ticker, interval: str = '1m', count: int = 1):
    """
    특정 Ticker의 최신 캔들 데이터를 거래소에서 가져와 DB에 저장합니다.
    """
    symbol = ticker.symbol 
    
    try:
        ohlcvs = await exchange.fetch_ohlcv(symbol, timeframe=interval, limit=count)
        if ohlcvs:
            await save_candles_to_db(ohlcvs, ticker, interval)
            # logger.info(f"✅ Stored {len(ohlcvs)} candles ({interval}) for {ticker.symbol}")
    except Exception as e:
        logger.error(f"❌ Failed to fetch candles ({interval}) for {ticker.symbol}: {e}")

async def fetch_historical_candles(exchange, ticker: Ticker, interval: str = '1d', days: int = 1825):
    """
    과거 데이터를 페이지네이션하여 대량으로 수집합니다.
    기본값: 1825일 (5년)
    """
    symbol = ticker.symbol
    limit_per_req = 200
    total_collected = 0
    
    # 'to' 파라미터는 가장 최근 수집된 캔들의 시간(가장 과거)을 기준으로 설정
    current_to = None 

    logger.info(f"📚 Fetching historical {interval} for {symbol} (target: {days} days)...")

    # 대략적인 루프 횟수 계산
    max_loops = (days // limit_per_req) + 5 
    
    for i in range(max_loops):
        try:
            params = {}
            if current_to:
                params['to'] = current_to.strftime("%Y-%m-%d %H:%M:%S")
            
            # Upbit는 to 파라미터 지원
            ohlcvs = await exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit_per_req, params=params)
            
            if not ohlcvs:
                break
                
            await save_candles_to_db(ohlcvs, ticker, interval)
            
            count = len(ohlcvs)
            total_collected += count
            
            # 다음 요청을 위한 'to' 설정: 받아온 데이터 중 가장 과거의 시간
            # ohlcvs[0]가 가장 과거 데이터 (CCXT 기본)
            oldest_ts = ohlcvs[0][0]
            oldest_dt = datetime.fromtimestamp(oldest_ts / 1000, tz=timezone.utc)
            
            # 중복 방지를 위해 1초 전으로 설정
            current_to = oldest_dt - timedelta(seconds=1)
            
            # 200개 단위로 로그 찍으면 너무 많을 수 있으므로 첫 배치와 500개 단위로만 찍거나, 디버그 레벨로 조정
            # 여기선 진행상황 확인을 위해 남겨둠
            logger.info(f"   - [{symbol}] Batch {i+1}: {count} candles. Oldest: {oldest_dt.date()}")

            if total_collected >= days:
                break
                
            if count < limit_per_req: # 더 이상 데이터가 없음
                break
                
            await asyncio.sleep(0.2) # Rate Limit
            
        except Exception as e:
            logger.error(f"❌ History fetch error for {symbol} at batch {i}: {e}")
            break
            
    logger.info(f"✅ Finished history fetch for {symbol}. Total: {total_collected}")

async def minute_collector_job():
    """매 분 실행되는 1분봉 수집 작업"""
    exchange = ccxt.upbit()
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(Ticker).where(Ticker.market_type == MarketType.CRYPTO, Ticker.is_active == True)
            result = await db.execute(stmt)
            tickers = result.scalars().all()
        
        if not tickers: return

        for ticker in tickers:
            await fetch_and_store_candles(exchange, ticker, interval='1m', count=3)
            await asyncio.sleep(0.1)
            
    except Exception as e:
        logger.error(f"🔥 Minute job error: {e}")
    finally:
        await exchange.close()

async def daily_collector_job():
    """매일 실행되는 일봉 수집 작업"""
    logger.info("🌞 Starting daily candle collection...")
    exchange = ccxt.upbit()
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(Ticker).where(Ticker.market_type == MarketType.CRYPTO, Ticker.is_active == True)
            result = await db.execute(stmt)
            tickers = result.scalars().all()
        
        if not tickers: return

        for ticker in tickers:
            # 일봉은 하루 1번이니 넉넉하게 최근 5일치 갱신
            await fetch_and_store_candles(exchange, ticker, interval='1d', count=5)
            await asyncio.sleep(0.1)
            
    except Exception as e:
        logger.error(f"🔥 Daily job error: {e}")
    finally:
        await exchange.close()

async def initial_seed():
    """최초 실행 시 과거 데이터 적재"""
    logger.info("🌱 Starting initial seed...")
    exchange = ccxt.upbit()
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(Ticker).where(Ticker.market_type == MarketType.CRYPTO, Ticker.is_active == True)
            result = await db.execute(stmt)
            tickers = result.scalars().all()

        if not tickers:
            logger.info("⚠️ No active tickers found.")
            return

        logger.info(f"🎯 Found {len(tickers)} tickers. Starting hydration...")

        for ticker in tickers:
            # 1. 최근 1분봉 200개 (빠르게)
            await fetch_and_store_candles(exchange, ticker, interval='1m', count=200)
            await asyncio.sleep(0.1)
            
            # 2. 일봉 5년치 (약 1800일) - 대량 수집
            await fetch_historical_candles(exchange, ticker, interval='1d', days=1825)
            await asyncio.sleep(0.1)
            
    except Exception as e:
        logger.error(f"🔥 Initial seed failed: {e}")
    finally:
        await exchange.close()

async def main():
    # 스케줄러를 먼저 띄우고 시드를 돌릴지, 시드를 다 돌리고 스케줄러를 띄울지 결정.
    # 시드가 오래 걸릴 수 있으므로(코인이 많으면), 스케줄러와 병행하거나
    # 여기서는 간단하게 시드 완료 후 스케줄러 실행 (블로킹)
    
    # 주의: 코인이 100개면 5년치 긁는데 개당 2초(10req * 0.2s) = 200초 = 3분 정도 소요됨.
    # 서버 시작 시 3분 대기는 허용 범위 내라고 판단.
    await initial_seed()

    scheduler = AsyncIOScheduler()
    
    # 1분봉: 매 분 5초
    scheduler.add_job(minute_collector_job, 'cron', second='5')
    
    # 일봉: 매일 오전 9시 1분
    scheduler.add_job(daily_collector_job, 'cron', hour='9', minute='1')
    
    scheduler.start()
    logger.info("🚀 Candle Collector Scheduler Started! (1m & 1d)")
    
    try:
        while True:
            await asyncio.sleep(1000)
    except (KeyboardInterrupt, SystemExit):
        pass

if __name__ == "__main__":
    asyncio.run(main())