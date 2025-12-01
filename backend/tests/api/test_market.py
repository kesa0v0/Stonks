import pytest
from httpx import AsyncClient
from datetime import datetime, timezone, timedelta
from backend.models.asset import MarketType, Currency, TickerSource, Ticker # TickerSource 추가
from backend.models.candle import Candle

@pytest.mark.asyncio
async def test_get_tickers(client: AsyncClient, db_session): # test_ticker fixture를 쓰지 않고 여기서 직접 Ticker를 만듦
    """
    Test retrieving the list of active tickers.
    """
    # 테스트용 티커 생성 (test_ticker fixture는 하나만 만드므로 여러 개를 위해 직접 생성)
    ticker1 = Ticker(id="TSLA", symbol="TSLA", name="Tesla Inc", market_type=MarketType.US, currency=Currency.USD, is_active=True, source=TickerSource.TEST)
    ticker2 = Ticker(id="AAPL", symbol="AAPL", name="Apple Inc", market_type=MarketType.US, currency=Currency.USD, is_active=True, source=TickerSource.TEST)
    ticker3 = Ticker(id="005930", symbol="005930", name="삼성전자", market_type=MarketType.KRX, currency=Currency.KRW, is_active=False, source=TickerSource.TEST) # Inactive
    
    db_session.add_all([ticker1, ticker2, ticker3])
    await db_session.commit()

    response = await client.get("/api/v1/market/tickers")
    
    assert response.status_code == 200
    tickers = response.json()
    
    assert isinstance(tickers, list)
    assert len(tickers) == 2 # Only active tickers should be returned
    
    # Check if correct tickers are returned
    returned_symbols = {t["symbol"] for t in tickers}
    assert "TSLA" in returned_symbols
    assert "AAPL" in returned_symbols
    assert "005930" not in returned_symbols # Inactive
    

@pytest.mark.asyncio
async def test_search_tickers(client: AsyncClient, db_session):
    """
    Test the /market/search endpoint.
    """
    # 테스트용 티커 생성
    ticker1 = Ticker(id="GOOG", symbol="GOOG", name="Alphabet Inc.", market_type=MarketType.US, currency=Currency.USD, is_active=True, source=TickerSource.TEST)
    ticker2 = Ticker(id="MSFT", symbol="MSFT", name="Microsoft Corp", market_type=MarketType.US, currency=Currency.USD, is_active=True, source=TickerSource.TEST)
    ticker3 = Ticker(id="BTCKRW", symbol="BTC/KRW", name="Bitcoin KRW", market_type=MarketType.CRYPTO, currency=Currency.KRW, is_active=True, source=TickerSource.TEST)
    ticker4 = Ticker(id="INFOCUS", symbol="FOCUS", name="InFocus Ltd", market_type=MarketType.US, currency=Currency.USD, is_active=False, source=TickerSource.TEST) # Inactive
    ticker5 = Ticker(id="APL", symbol="APL", name="Apple", market_type=MarketType.US, currency=Currency.USD, is_active=True, source=TickerSource.TEST)

    db_session.add_all([ticker1, ticker2, ticker3, ticker4, ticker5])
    await db_session.commit()

    # Case 1: Search by full symbol (case-insensitive)
    response = await client.get("/api/v1/market/search", params={"query": "goog"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "GOOG"

    # Case 2: Search by partial name (case-insensitive)
    response = await client.get("/api/v1/market/search", params={"query": "soft"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Microsoft Corp"

    # Case 3: Search by part of symbol
    response = await client.get("/api/v1/market/search", params={"query": "tc"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "BTC/KRW"
    
    # Case 4: Search with multiple matches
    response = await client.get("/api/v1/market/search", params={"query": "Apple"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1 # 'Apple Inc' (name) or 'APL' (symbol) - only one with 'Apple' name
    assert data[0]["name"] == "Apple"

    # Case 5: Inactive ticker should not be returned
    response = await client.get("/api/v1/market/search", params={"query": "InFocus"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0 # Inactive ticker should not be returned

    # Case 6: No matching results
    response = await client.get("/api/v1/market/search", params={"query": "XYZ"})
    assert response.status_code == 200
    assert response.json() == []

    # Case 7: Limit parameter
    response = await client.get("/api/v1/market/search", params={"query": "c", "limit": 1}) # "c" matches MicroSoft and Bitcoin
    assert response.status_code == 200
    data = response.json() # Update data variable
    assert len(data) == 1
    
    # Case 8: Invalid query (too short)
    response = await client.get("/api/v1/market/search", params={"query": ""})
    assert response.status_code == 422


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
    response = await client.get(f"/api/v1/market/candles/{test_ticker}", params={"interval": "1m", "limit": 3})
    
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
    response = await client.get(f"/api/v1/market/candles/{test_ticker}", params={"interval": "1h"}) # 1h is not allowed
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
    
    response = await client.get(f"/api/v1/market/candles/NON_EXISTENT_TICKER", params={"interval": "1m"})
    assert response.status_code == 200
    assert response.json() == []
