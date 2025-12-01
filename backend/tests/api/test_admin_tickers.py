import pytest
from httpx import AsyncClient
from backend.models import Ticker, MarketType, Currency, TickerSource
from backend.core.security import create_access_token

@pytest.mark.asyncio
async def test_admin_create_ticker(client: AsyncClient, db_session, admin_user_token):
    """
    Test creating a new ticker by admin.
    """
    headers = {"Authorization": f"Bearer {admin_user_token}"}
    payload = {
        "id": "KRW-ETH", # ID 직접 지정
        "symbol": "ETH",
        "name": "Ethereum",
        "market_type": "CRYPTO",
        "currency": "KRW",
        "source": "TEST",
        "is_active": True
    }
    
    response = await client.post("/api/v1/admin/tickers", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    
    assert data["id"] == "KRW-ETH" 
    assert data["symbol"] == "ETH"
    assert data["source"] == "TEST"

@pytest.mark.asyncio
async def test_admin_update_ticker(client: AsyncClient, db_session, admin_user_token):
    """
    Test updating an existing ticker.
    """
    # 1. Create ticker first
    ticker = Ticker(id="US-TSLA", symbol="TSLA", name="Tesla", market_type=MarketType.US, currency=Currency.USD)
    db_session.add(ticker)
    await db_session.commit()
    
    headers = {"Authorization": f"Bearer {admin_user_token}"}
    payload = {
        "name": "Tesla Inc." # Update name
    }
    
    response = await client.put("/api/v1/admin/tickers/US-TSLA", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    
    assert data["name"] == "Tesla Inc."
    assert data["id"] == "US-TSLA"

@pytest.mark.asyncio
async def test_admin_delete_ticker(client: AsyncClient, db_session, admin_user_token):
    """
    Test deleting a ticker.
    """
    # 1. Create ticker
    ticker = Ticker(id="DELETE-ME", symbol="DEL", name="Delete Me", market_type=MarketType.KRX, currency=Currency.KRW)
    db_session.add(ticker)
    await db_session.commit()
    
    headers = {"Authorization": f"Bearer {admin_user_token}"}
    
    # 2. Delete
    response = await client.delete("/api/v1/admin/tickers/DELETE-ME", headers=headers)
    assert response.status_code == 200
    
    # 3. Verify deletion
    response = await client.get("/api/v1/market/search", params={"query": "DEL"})
    # It might return empty list or 404 depending on search implementation, 
    # but since we deleted it, search should not find it.
    assert response.status_code == 200
    tickers = response.json()
    assert len(tickers) == 0

@pytest.mark.asyncio
async def test_admin_ticker_permission(client: AsyncClient, another_user_token):
    """
    Test that non-admin users cannot manage tickers.
    """
    headers = {"Authorization": f"Bearer {another_user_token}"}
    payload = {
        "id": "HACK-COIN", # ID 추가
        "symbol": "HACK",
        "name": "Hack Coin",
        "market_type": "CRYPTO",
        "currency": "KRW"
    }
    
    response = await client.post("/api/v1/admin/tickers", json=payload, headers=headers)
    assert response.status_code == 403
