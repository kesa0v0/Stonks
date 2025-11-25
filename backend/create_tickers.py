# backend/create_tickers.py
from backend.core.database import SessionLocal
from backend.models import Ticker, MarketType, Currency

db = SessionLocal()

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
    # 나중에 삼성전자 등도 여기에 추가하면 됩니다.
]

try:
    print("🚀 Initializing Tickers...")
    for item in INITIAL_TICKERS:
        existing = db.query(Ticker).filter(Ticker.id == item["id"]).first()
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
    
    db.commit()
    print("🎉 Ticker initialization complete!")

except Exception as e:
    print(f"❌ Error: {e}")
    db.rollback()
finally:
    db.close()