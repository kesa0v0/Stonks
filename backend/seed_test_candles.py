import asyncio
import random
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from backend.core.database import AsyncSessionLocal
from backend.models import Ticker, Candle, TickerSource

# 설정
DAYS_HISTORY = 30      # 일봉 생성 기간 (일)
MINUTES_HISTORY = 11520 # 분봉 생성 기간 (분, 11520분 = 8일) -> 1W 차트 지원
START_PRICE = 10000.0
VOLATILITY_DAILY = 0.05 # 일봉 변동성 (5%)
VOLATILITY_MINUTE = 0.005 # 분봉 변동성 (0.5%)

async def generate_random_candles(ticker_id, interval, start_time, count, volatility, current_price):
    candles = []
    price = current_price
    
    # 시간 간격 설정
    delta = timedelta(days=1) if interval == '1d' else timedelta(minutes=1)
    
    for i in range(count):
        timestamp = start_time + (delta * i)
        
        # 랜덤 변동 (-volatility ~ +volatility)
        change_pct = random.uniform(-volatility, volatility)
        close_price = price * (1 + change_pct)
        
        # 고가/저가 생성 (시가/종가 기준으로 약간의 위아래 꼬리)
        high_price = max(price, close_price) * (1 + random.uniform(0, volatility/2))
        low_price = min(price, close_price) * (1 - random.uniform(0, volatility/2))
        
        # 거래량 랜덤
        volume = random.uniform(100, 10000)

        candles.append({
            "ticker_id": ticker_id,
            "timestamp": timestamp,
            "interval": interval,
            "open": price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume
        })
        
        price = close_price # 다음 봉의 시가는 현재 봉의 종가
        
    return candles, price

async def seed_test_candles():
    print("🌱 Seeding TEST candles...")
    
    async with AsyncSessionLocal() as db:
        # 1. TEST 티커 조회
        stmt = select(Ticker).where(Ticker.source == TickerSource.TEST)
        result = await db.execute(stmt)
        tickers = result.scalars().all()
        
        if not tickers:
            print("⚠️ No tickers with source=TEST found.")
            return

        print(f"🎯 Found {len(tickers)} TEST tickers.")

        for ticker in tickers:
            print(f"   - Generating candles for {ticker.symbol}...")
            
            # 기준 시간 (UTC)
            now = datetime.now(timezone.utc)
            
            # 2. 일봉 생성 (30일 전부터 어제까지)
            start_daily = now - timedelta(days=DAYS_HISTORY)
            daily_candles, last_daily_price = await generate_random_candles(
                ticker.id, '1d', start_daily, DAYS_HISTORY, VOLATILITY_DAILY, START_PRICE
            )
            
            # 3. 분봉 생성 (어제부터 현재까지)
            # 분봉 시작 가격은 일봉의 마지막 종가로 이어지게 함
            start_minute = now - timedelta(minutes=MINUTES_HISTORY)
            minute_candles, _ = await generate_random_candles(
                ticker.id, '1m', start_minute, MINUTES_HISTORY, VOLATILITY_MINUTE, last_daily_price
            )
            
            all_candles = daily_candles + minute_candles
            
            # 4. DB 저장 (Bulk Upsert)
            # 1000개씩 끊어서 저장
            batch_size = 1000
            for i in range(0, len(all_candles), batch_size):
                batch = all_candles[i:i+batch_size]
                
                stmt = insert(Candle).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['ticker_id', 'timestamp', 'interval'],
                    set_={
                        'open': stmt.excluded.open,
                        'high': stmt.excluded.high,
                        'low': stmt.excluded.low,
                        'close': stmt.excluded.close,
                        'volume': stmt.excluded.volume
                    }
                )
                await db.execute(stmt)
            
            print(f"     ✅ Inserted {len(all_candles)} candles.")
            
        await db.commit()
        print("🎉 Done!")

if __name__ == "__main__":
    asyncio.run(seed_test_candles())
