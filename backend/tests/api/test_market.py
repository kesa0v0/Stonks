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

@pytest.mark.asyncio
async def test_get_movers(client: AsyncClient, db_session):
    """
    Test /market/movers endpoint for Gainers and Losers.
    """
    # Create Tickers
    t1 = Ticker(id="T1", symbol="T1", name="Ticker 1", market_type=MarketType.US, currency=Currency.USD, is_active=True, source=TickerSource.TEST)
    t2 = Ticker(id="T2", symbol="T2", name="Ticker 2", market_type=MarketType.US, currency=Currency.USD, is_active=True, source=TickerSource.TEST)
    t3 = Ticker(id="T3", symbol="T3", name="Ticker 3", market_type=MarketType.US, currency=Currency.USD, is_active=True, source=TickerSource.TEST)
    db_session.add_all([t1, t2, t3])
    await db_session.commit()

    base_time = datetime.now(timezone.utc)

    # Create 1d Candles (Previous Close)
    # T1: Prev=100
    # T2: Prev=100
    # T3: Prev=100
    c1_prev = Candle(ticker_id="T1", timestamp=base_time - timedelta(days=1), interval="1d", open=100, high=100, low=100, close=100, volume=100)
    c2_prev = Candle(ticker_id="T2", timestamp=base_time - timedelta(days=1), interval="1d", open=100, high=100, low=100, close=100, volume=100)
    c3_prev = Candle(ticker_id="T3", timestamp=base_time - timedelta(days=1), interval="1d", open=100, high=100, low=100, close=100, volume=100)
    
    # Create 1m Candles (Current Price)
    # T1: Curr=110 (+10%)
    # T2: Curr=90 (-10%)
    # T3: Curr=100 (0%)
    c1_curr = Candle(ticker_id="T1", timestamp=base_time, interval="1m", open=110, high=110, low=110, close=110, volume=100)
    c2_curr = Candle(ticker_id="T2", timestamp=base_time, interval="1m", open=90, high=90, low=90, close=90, volume=100)
    c3_curr = Candle(ticker_id="T3", timestamp=base_time, interval="1m", open=100, high=100, low=100, close=100, volume=100)

    db_session.add_all([c1_prev, c2_prev, c3_prev, c1_curr, c2_curr, c3_curr])
    await db_session.commit()

    # Test Gainers
    res_gainers = await client.get("/api/v1/market/movers", params={"type": "gainers"})
    assert res_gainers.status_code == 200
    gainers = res_gainers.json()
    assert len(gainers) == 3
    assert gainers[0]["ticker"]["symbol"] == "T1"
    assert gainers[0]["change_percent"] == "10.00"

    # Test Losers
    res_losers = await client.get("/api/v1/market/movers", params={"type": "losers"})
    assert res_losers.status_code == 200
    losers = res_losers.json()
    assert len(losers) == 3
    assert losers[0]["ticker"]["symbol"] == "T2"
    assert losers[0]["change_percent"] == "-10.00"

@pytest.mark.asyncio
async def test_get_trending(client: AsyncClient, db_session):
    """
    Test /market/trending endpoint.
    """
    # Create Tickers
    t1 = Ticker(id="T4", symbol="T4", name="Ticker 4", market_type=MarketType.US, currency=Currency.USD, is_active=True, source=TickerSource.TEST)
    t2 = Ticker(id="T5", symbol="T5", name="Ticker 5", market_type=MarketType.US, currency=Currency.USD, is_active=True, source=TickerSource.TEST)
    db_session.add_all([t1, t2])
    await db_session.commit()

    base_time = datetime.now(timezone.utc)

    # Prev Candles (needed for change_percent calculation)
    c1_prev = Candle(ticker_id="T4", timestamp=base_time - timedelta(days=1), interval="1d", open=100, high=100, low=100, close=100, volume=100)
    c2_prev = Candle(ticker_id="T5", timestamp=base_time - timedelta(days=1), interval="1d", open=100, high=100, low=100, close=100, volume=100)

    # Current 1m Candles
    # T4: Price=100, Vol=1000 -> Value = 100,000
    # T5: Price=100, Vol=10 -> Value = 1,000
    c1_curr = Candle(ticker_id="T4", timestamp=base_time, interval="1m", open=100, high=100, low=100, close=100, volume=1000)
    c2_curr = Candle(ticker_id="T5", timestamp=base_time, interval="1m", open=100, high=100, low=100, close=100, volume=10)

    db_session.add_all([c1_prev, c2_prev, c1_curr, c2_curr])
    await db_session.commit()

    res = await client.get("/api/v1/market/trending")
    assert res.status_code == 200
    trends = res.json()
    assert len(trends) == 2
    assert trends[0]["ticker"]["symbol"] == "T4"
    assert float(trends[0]["value"]) > float(trends[1]["value"])