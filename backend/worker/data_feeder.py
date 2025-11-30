import asyncio
import json
import redis.asyncio as redis
import ccxt.pro as ccxt  # or ccxt for standard
import ccxt.async_support as ccxt_async  # 비동기 지원 모듈

from backend.core.event_hook import publish_event
from backend.core.config import settings

# 수집할 대상 목록
TARGET_TICKERS = {
    "BTC/KRW": "CRYPTO-COIN-BTC",
    "ETH/KRW": "CRYPTO-COIN-ETH",
    "DOGE/KRW": "CRYPTO-COIN-DOGE",
}

async def fetch_and_publish():
    r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)
    exchange = ccxt_async.upbit()
    
    # 수집할 심볼 리스트 미리 만들기 (['BTC/KRW', 'ETH/KRW'])
    symbols = list(TARGET_TICKERS.keys()) 

    print(f"🚀 Data Feeder Started! Targets: {symbols}")

    try:
        while True:
            try:
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
                    await r.set(f"price:{ticker_id}", json.dumps(data))
                    await r.publish("market_updates", json.dumps(data))

                    # Price Update Hook: 가격 변동 이벤트 발행
                    event = {
                        "type": "price_updated",
                        "ticker_id": ticker_id,
                        "price": price,
                        "timestamp": ticker['timestamp']
                    }
                    await publish_event(r, event)

                    print(f"✅ {symbol}: {price:,.0f} KRW (event published)")

            except Exception as e:
                print(f"❌ Error: {e}")

            await asyncio.sleep(1) # 1초 휴식

    except KeyboardInterrupt:
        print("🛑 Worker stopped.")
    finally:
        await exchange.close()
        await r.close()

if __name__ == "__main__":
    asyncio.run(fetch_and_publish())