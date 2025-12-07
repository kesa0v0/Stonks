import asyncio
import json
import redis.asyncio as redis
import ccxt.async_support as ccxt_async
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import (
    EVENT_JOB_MISSED,
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
)
from datetime import datetime, timezone, timedelta
import logging
import time

from sqlalchemy import select # New import
from backend.core.database import AsyncSessionLocal # New import
from backend.models.asset import Ticker # New import (Ticker model is in asset.py)

from backend.core.event_hook import publish_event
from backend.core.config import settings

# 로깅 설정
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("data_feeder")

# APScheduler 로그 레벨 조정
logging.getLogger('apscheduler.executors.default').setLevel(logging.ERROR)
logging.getLogger('apscheduler.scheduler').setLevel(logging.ERROR)

# 수집할 대상 목록 (초기화)
TARGET_TICKERS = {} # Will be populated dynamically

exchange = None
redis_client = None
tick_counter = 0

async def get_active_tickers_from_db() -> dict:
    """Fetches active tickers from the database and returns them in a symbol:ticker_id map."""
    active_tickers = {}
    async with AsyncSessionLocal() as db:
        stmt = select(Ticker).where(Ticker.is_active == True)
        tickers = (await db.execute(stmt)).scalars().all()
        for ticker in tickers:
            active_tickers[ticker.symbol] = ticker.id
    return active_tickers

async def init_resources():
    global exchange, redis_client, TARGET_TICKERS
    exchange = ccxt_async.upbit({'enableRateLimit': True, 'timeout': 10000})
    redis_client = redis.Redis(
        host=settings.REDIS_HOST, 
        port=settings.REDIS_PORT, 
        decode_responses=True
    )
    try:
        # Warm up markets to avoid symbol resolution issues
        await exchange.load_markets()
        logger.info("✅ Upbit markets loaded")
    except Exception as e:
        logger.warning(f"⚠️ load_markets failed: {e}")

    # Dynamically load active tickers
    TARGET_TICKERS = await get_active_tickers_from_db()
    if not TARGET_TICKERS:
        logger.error("❌ No active tickers found in DB. Data feeder will not fetch any data.")
    else:
        logger.info(f"Loaded {len(TARGET_TICKERS)} active tickers from DB: {list(TARGET_TICKERS.keys())}")

async def fetch_tickers_job():
    """
    주기적으로 실행될 작업: 시세 조회 및 Redis 발행
    """
    try:
        if exchange is None or redis_client is None:
            logger.warning("⚠️ Resources not ready for fetch_tickers_job")
            return
        
        # Check if TARGET_TICKERS was populated
        if not TARGET_TICKERS:
            logger.warning("⚠️ No TARGET_TICKERS defined. Skipping fetch_tickers_job.")
            return

        symbols = list(TARGET_TICKERS.keys())
        # 전체 실행시간 측정 (요청+발행 포함)
        t0 = time.perf_counter()
        # [핵심] fetch_tickers (복수형) 사용 -> 요청 1번으로 모든 시세 가져옴!
        try:
            tickers = await exchange.fetch_tickers(symbols)
        except Exception as e:
            # Fallback: fetch individually to avoid total failure
            logger.warning(f"⚠️ fetch_tickers failed, falling back per symbol: {e}")
            tickers = {}
            for s in symbols:
                try:
                    t = await exchange.fetch_ticker(s)
                    tickers[s] = t
                except Exception as se:
                    logger.warning(f"⚠️ fetch_ticker({s}) error: {se}")
        
        for symbol, ticker in tickers.items():
            ticker_id = TARGET_TICKERS[symbol]
            price = ticker.get('last')
            if price is None:
                # Try bid/ask mid
                bid = ticker.get('bid') or (ticker.get('bids') or [None])[0]
                ask = ticker.get('ask') or (ticker.get('asks') or [None])[0]
                if isinstance(bid, (list, tuple)):
                    bid = bid[0]
                if isinstance(ask, (list, tuple)):
                    ask = ask[0]
                if bid is not None and ask is not None:
                    try:
                        price = (float(bid) + float(ask)) / 2.0
                    except Exception:
                        price = None
            if price is None:
                # Skip if still no price
                logger.warning(f"⚠️ No price for {symbol}, skipping")
                continue
            
            data = {
                "type": "ticker",
                "ticker_id": ticker_id,
                "price": price,
                "timestamp": ticker['timestamp']
            }
            
            # Redis 저장 & 발행
            await redis_client.set(f"price:{ticker_id}", json.dumps(data))
            await redis_client.publish("market_updates", json.dumps(data))

            # Price Update Hook: 가격 변동 이벤트 발행
            event = {
                "type": "price_updated",
                "ticker_id": ticker_id,
                "price": price,
                "timestamp": ticker['timestamp']
            }
            await publish_event(redis_client, event, channel="price_events")

        elapsed = time.perf_counter() - t0
        if elapsed > 0.8:
            logger.warning(f"⏱️ fetch_tickers_job slow run: {elapsed:.3f}s; consider reducing symbols or raising interval")

    except Exception as e:
        logger.error(f"❌ Fetch Tickers Error: {e}", exc_info=True)
        # Attempt to recreate exchange on hard failures
        try:
            if exchange:
                await exchange.close()
        except Exception:
            pass
        try:
            await asyncio.sleep(1)
            await init_resources()
            logger.info("🔁 Exchange reinitialized after error")
        except Exception as re:
            logger.error(f"❌ Failed to reinitialize exchange: {re}")

async def fetch_orderbooks_job():
    """
    주기적으로 실행될 작업: 호가창 조회 및 Redis 발행
    """
    try:
        if exchange is None or redis_client is None:
            logger.warning("⚠️ Resources not ready for fetch_orderbooks_job")
            return
        
        # Check if TARGET_TICKERS was populated
        if not TARGET_TICKERS:
            logger.warning("⚠️ No TARGET_TICKERS defined. Skipping fetch_orderbooks_job.")
            return

        t0 = time.perf_counter()
        ex = exchange  # capture to satisfy type checkers
        rc = redis_client

        async def _fetch_one(symbol: str, ticker_id: str):
            try:
                orderbook = await ex.fetch_order_book(symbol, limit=15)
                formatted_asks = [{"price": ask[0], "quantity": ask[1]} for ask in orderbook.get('asks', [])]
                formatted_bids = [{"price": bid[0], "quantity": bid[1]} for bid in orderbook.get('bids', [])]
                data = {
                    "type": "orderbook",
                    "ticker_id": ticker_id,
                    "asks": formatted_asks,
                    "bids": formatted_bids,
                    "timestamp": orderbook.get('timestamp')
                }
                await rc.set(f"orderbook:{ticker_id}", json.dumps(data))
                await rc.publish("orderbook_updates", json.dumps(data))
            except Exception as sub_e:
                logger.warning(f"⚠️ Fetch Orderbook Error ({symbol}): {sub_e}")

        tasks = [_fetch_one(symbol, ticker_id) for symbol, ticker_id in TARGET_TICKERS.items()]
        if tasks:
            await asyncio.gather(*tasks)

        elapsed = time.perf_counter() - t0
        if elapsed > 0.9:
            logger.warning(f"⏱️ fetch_orderbooks_job slow run: {elapsed:.3f}s; consider seconds=2 or reducing symbols")

    except Exception as e:
        logger.error(f"❌ Fetch Orderbooks Job Error: {e}", exc_info=True)

async def market_feeder_job():
    """Single consolidated job: tickers every 1s, orderbooks every 2s with time budget."""
    global tick_counter
    start = time.perf_counter()
    await fetch_tickers_job()
    elapsed_after_tickers = time.perf_counter() - start
    budget = 0.95
    if tick_counter % 2 == 0:
        if elapsed_after_tickers < budget * 0.7:
            try:
                await fetch_orderbooks_job()
            except Exception as e:
                logger.warning(f"⚠️ market_feeder_job orderbooks error: {e}")
        else:
            logger.info(f"ℹ️ Skipping orderbooks this tick to keep schedule (elapsed={elapsed_after_tickers:.3f}s)")
    total = time.perf_counter() - start
    if total > budget:
        logger.warning(f"⏱️ market_feeder_job slow run: {total:.3f}s; consider raising interval or reducing work")
    tick_counter = (tick_counter + 1) % 1000000

async def main():
    await init_resources()
    
    scheduler = AsyncIOScheduler()
    
    # 상세 원인 로깅을 위한 스케줄러 리스너
    def _scheduler_listener(event):
        now = datetime.now(timezone.utc)
        scheduled = getattr(event, 'scheduled_run_time', None)
        delay_str = ""
        if scheduled is not None:
            try:
                delay = (now - scheduled).total_seconds()
                delay_str = f" | delay={delay:.3f}s"
            except Exception:
                pass

        if event.code == EVENT_JOB_MISSED:
            logger.warning(
                f"⏰ JOB MISSED id={getattr(event, 'job_id', '?')} sched={scheduled}Z | now={now.isoformat()}Z{delay_str}. "
                "Likely causes: long-running job, process busy, or clock skew."
            )
        elif event.code == EVENT_JOB_MAX_INSTANCES:
            logger.warning(
                f"🚦 JOB SKIPPED (max_instances) id={getattr(event, 'job_id', '?')} sched={scheduled}Z | now={now.isoformat()}Z{delay_str}. "
                "Consider increasing max_instances or reducing job duration."
            )
        elif event.code == EVENT_JOB_ERROR:
            logger.error(
                f"💥 JOB ERROR id={getattr(event, 'job_id', '?')} sched={scheduled}Z | now={now.isoformat()}Z{delay_str} | "
                f"exc={getattr(event, 'exception', None)}"
            )
        # Do not log EXECUTED to reduce noise

    scheduler.add_listener(
        _scheduler_listener,
        EVENT_JOB_MISSED | EVENT_JOB_MAX_INSTANCES | EVENT_JOB_ERROR,
    )
    # 1초마다 단일 잡 실행 (내부에서 2틱마다 orderbooks 실행)
    scheduler.add_job(
        market_feeder_job,
        'interval',
        seconds=2, # Increased from 1 to 2 seconds
        id='market_feeder_job',
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3,
    )
    scheduler.start()
    
    logger.info("🚀 Data Feeder Started with APScheduler (1s interval)")
    
    try:
        # 메인 루프 유지 (스케줄러가 백그라운드에서 동작)
        while True:
            await asyncio.sleep(1000)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("🛑 Worker stopping...")
    finally:
        if exchange:
            await exchange.close()
        if redis_client:
            await redis_client.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass