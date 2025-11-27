# backend/create_tickers.py
import asyncio
from sqlalchemy import select
from backend.core.database import AsyncSessionLocal
from backend.models import Ticker, MarketType, Currency

# 등록할 종목 리스트
INITIAL_TICKERS = [
    {
        "id": "CRYPTO-COIN-BTC",
        "symbol": "BTC/KRW",
        "name": "Bitcoin",
        "market_type": MarketType.CRYPTO,
        "currency": Currency.KRW
    },
    {
        "id": "CRYPTO-COIN-ETH",
        "symbol": "ETH/KRW",
        "name": "Ethereum",
        "market_type": MarketType.CRYPTO,
        "currency": Currency.KRW
    },
    {
        "id": "CRYPTO-COIN-DOGE",
        "symbol": "DOGE/KRW",
        "name": "Dogecoin",
        "market_type": MarketType.CRYPTO,
        "currency": Currency.KRW
    },
    {
        "id": "TEST-COIN",
        "symbol": "TEST/KRW",
        "name": "Volatility Test Coin",
        "market_type": MarketType.CRYPTO,
        "currency": Currency.KRW
    },
]

async def init_tickers():
    print("🚀 Initializing Tickers...")
    async with AsyncSessionLocal() as db:
        try:
            for item in INITIAL_TICKERS:
                result = await db.execute(select(Ticker).where(Ticker.id == item["id"]))
                existing = result.scalars().first()
                
                if not existing:
                    ticker = Ticker(
                        id=item["id"],
                        symbol=item["symbol"],
                        name=item["name"],
                        market_type=item["market_type"],
                        currency=item["currency"]
                    )
                    db.add(ticker)
                    print(f"✅ Added: {item['name']} ({item['id']})")
                else:
                    print(f"ℹ️ Already exists: {item['name']}")
            
            await db.commit()
            print("🎉 Ticker initialization complete!")

        except Exception as e:
            print(f"❌ Error: {e}")
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(init_tickers())
