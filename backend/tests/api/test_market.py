import pytest
from httpx import AsyncClient
from datetime import datetime, timezone, timedelta
from backend.models.asset import MarketType, Currency
from backend.models.candle import Candle

@pytest.mark.asyncio
async def test_get_tickers(client: AsyncClient, test_ticker):
    """
    Test retrieving the list of active tickers.
    """
    response = await client.get("/market/tickers")
    
    assert response.status_code == 200
    tickers = response.json()
    
    assert isinstance(tickers, list)
    assert len(tickers) >= 1 # At least 'test_ticker' should be there
    
    # Find our test ticker
    found_ticker = next((t for t in tickers if t["id"] == test_ticker), None)
    assert found_ticker is not None
    assert found_ticker["symbol"] == "TEST/KRW"
    assert found_ticker["market_type"] == MarketType.CRYPTO.value
    assert found_ticker["currency"] == Currency.KRW.value
    assert found_ticker["is_active"] is True

@pytest.mark.asyncio
async def test_get_candles(client: AsyncClient, db_session, test_ticker):
    """
    Test retrieving candle data for a specific ticker.
    """
    # 1. Prepare test data (Candles)
    base_time = datetime.now(timezone.utc)
    candles = []
    # Create 5 candles, 1 minute apart
    for i in range(5):
        candles.append(Candle(
            ticker_id=test_ticker,
            timestamp=base_time - timedelta(minutes=i),
            interval="1m",
            open=100 + i,
            high=110 + i,
            low=90 + i,
            close=105 + i,
            volume=1000
        ))
    
    db_session.add_all(candles)
    await db_session.commit()
    
    # 2. Request candles
    response = await client.get(f"/market/candles/{test_ticker}", params={"interval": "1m", "limit": 3})
    
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)
    assert len(data) == 3 # limit check
    
    # 3. Verify sort order (Ascending by timestamp)
    # API returns reversed(descending result), so it should be ascending
    first_candle = data[0]
    last_candle = data[-1]
    
    first_ts = datetime.fromisoformat(first_candle["timestamp"])
    last_ts = datetime.fromisoformat(last_candle["timestamp"])
    
    assert first_ts < last_ts
    
    # 4. Verify data integrity
    assert first_candle["ticker_id"] == test_ticker
    assert "open" in first_candle
    assert "close" in first_candle

@pytest.mark.asyncio
async def test_get_candles_invalid_interval(client: AsyncClient, test_ticker):
    """
    Test validation error for invalid interval.
    """
    response = await client.get(f"/market/candles/{test_ticker}", params={"interval": "1h"}) # 1h is not allowed
    assert response.status_code == 422 # Unprocessable Entity

@pytest.mark.asyncio
async def test_get_candles_empty(client: AsyncClient, test_ticker):
    """
    Test retrieving candles for a ticker with no data.
    """
    # Use a ticker that has no candles (test_ticker initially has none unless added in test)
    # But previous test might have added some. Let's use a non-existent ID or assume test isolation.
    # With function-scoped db_session, data should be isolated if fixture cleans up properly.
    # However, test_ticker fixture creates the ticker. 
    
    # Let's assume isolation. If not, we might get data.
    # To be safe, we can query a non-existent ticker, but the API doesn't 404 on empty, just returns [].
    
    response = await client.get(f"/market/candles/NON_EXISTENT_TICKER", params={"interval": "1m"})
    assert response.status_code == 200
    assert response.json() == []
