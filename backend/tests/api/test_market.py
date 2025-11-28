import pytest
from httpx import AsyncClient
from backend.models.asset import MarketType, Currency

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
