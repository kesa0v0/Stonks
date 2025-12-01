import asyncio
import json
import redis.asyncio as redis
import ccxt.async_support as ccxt_async
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.core.event_hook import publish_event
from backend.core.config import settings

# 수집할 대상 목록
TARGET_TICKERS = {
    "BTC/KRW": "CRYPTO-COIN-BTC",
    "ETH/KRW": "CRYPTO-COIN-ETH",
    "DOGE/KRW": "CRYPTO-COIN-DOGE",
}

exchange = None
redis_client = None

async def init_resources():
    global exchange, redis_client
    exchange = ccxt_async.upbit()
    redis_client = redis.Redis(
        host=settings.REDIS_HOST, 
        port=settings.REDIS_PORT, 
        decode_responses=True
    )

async def fetch_tickers_job():
    """
    주기적으로 실행될 작업: 시세 조회 및 Redis 발행
    """
    try:
        symbols = list(TARGET_TICKERS.keys())
        # [핵심] fetch_tickers (복수형) 사용 -> 요청 1번으로 모든 시세 가져옴!
        tickers = await exchange.fetch_tickers(symbols)
        
        for symbol, ticker in tickers.items():
            ticker_id = TARGET_TICKERS[symbol]
            price = ticker['last']
            
            data = {
                "ticker_id": ticker_id,
                "price": price,
                "timestamp": ticker['timestamp']
            }
            
            # Redis 저장 & 발행
            # 파이프라인을 사용하여 Redis 요청 최적화 가능하지만, publish는 즉시 전파가 중요하므로 개별 실행이 나을 수도 있음.
            # 여기선 단순하게 개별 실행.
            await redis_client.set(f"price:{ticker_id}", json.dumps(data))
            await redis_client.publish("market_updates", json.dumps(data))

            # Price Update Hook: 가격 변동 이벤트 발행
            event = {
                "type": "price_updated",
                "ticker_id": ticker_id,
                "price": price,
                "timestamp": ticker['timestamp']
            }
            # publish_event 내부 로직이 복잡하지 않다면 직접 publish 호출해도 됨 (오버헤드 절감)
            # 하지만 일관성을 위해 함수 사용
            await publish_event(redis_client, event, channel="price_events")

            # print(f"✅ {symbol}: {price:,.0f} KRW") # 로그 노이즈 감소를 위해 주석 처리

    except Exception as e:
        print(f"❌ Fetch Error: {e}")

async def main():
    await init_resources()
    
    scheduler = AsyncIOScheduler()
    # 1초마다 실행.
    # max_instances=1: 이전 작업이 끝나지 않았으면 건너뜀 (중복 실행 방지)
    # coalesce=True: 여러 번 실행 기회를 놓쳐도 한 번만 실행 (밀림 방지)
    scheduler.add_job(fetch_tickers_job, 'interval', seconds=1, max_instances=1, coalesce=True)
    scheduler.start()
    
    print("🚀 Data Feeder Started with APScheduler (1s interval)")
    
    try:
        # 메인 루프 유지 (스케줄러가 백그라운드에서 동작)
        while True:
            await asyncio.sleep(1000)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("🛑 Worker stopping...")
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