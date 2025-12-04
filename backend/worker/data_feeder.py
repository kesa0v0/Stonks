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

    except Exception as e:
        print(f"❌ Fetch Tickers Error: {e}")

async def fetch_orderbooks_job():
    """
    주기적으로 실행될 작업: 호가창 조회 및 Redis 발행
    """
    try:
        for symbol, ticker_id in TARGET_TICKERS.items():
            try:
                # ccxt fetch_order_book returns: {'bids': [[price, qty], ...], 'asks': [[price, qty], ...], ...}
                orderbook = await exchange.fetch_order_book(symbol, limit=15)
                
                # Format data
                # asks: 매도 잔량 (Price 오름차순 - 싸게 팔려는 사람 우선)
                # bids: 매수 잔량 (Price 내림차순 - 비싸게 사려는 사람 우선)
                formatted_asks = [{"price": ask[0], "quantity": ask[1]} for ask in orderbook['asks']]
                formatted_bids = [{"price": bid[0], "quantity": bid[1]} for bid in orderbook['bids']]

                data = {
                    "type": "orderbook",
                    "ticker_id": ticker_id,
                    "asks": formatted_asks,
                    "bids": formatted_bids,
                    "timestamp": orderbook.get('timestamp')
                }
                
                # Publish to Redis channel "orderbook_updates"
                # Note: We don't necessarily need to store full orderbook in Redis key if not queried often by REST
                # But for caching REST API response, we might want to set it.
                # Let's set a key for initial REST load as well.
                await redis_client.set(f"orderbook:{ticker_id}", json.dumps(data))
                await redis_client.publish("orderbook_updates", json.dumps(data))
                
            except Exception as sub_e:
                print(f"⚠️ Fetch Orderbook Error ({symbol}): {sub_e}")

    except Exception as e:
        print(f"❌ Fetch Orderbooks Job Error: {e}")

async def main():
    await init_resources()
    
    scheduler = AsyncIOScheduler()
    # 1초마다 실행.
    scheduler.add_job(fetch_tickers_job, 'interval', seconds=1, max_instances=1, coalesce=True)
    scheduler.add_job(fetch_orderbooks_job, 'interval', seconds=1, max_instances=1, coalesce=True)
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