import pytest
from httpx import AsyncClient
from backend.models import Portfolio
from decimal import Decimal

@pytest.mark.asyncio
async def test_get_ticker_price(client: AsyncClient, test_ticker, mock_external_services):
    """
    Test retrieving current price for a ticker.
    """
    # Mock Redis has "price:TEST-COIN" -> 100.0 (from conftest)
    
    # Note: The endpoint requires an API Key or valid User Token. 
    # The client fixture authenticates as test_user by default if no headers provided?
    # Actually client fixture overrides get_current_user to return test_user.
    # But /market/price/{ticker_id} uses `get_current_user_by_api_key` security scheme.
    # We need to check if `client` fixture supports this.
    # The endpoint `get_ticker_current_price` uses `Security(get_current_user_by_api_key)`.
    # If we use standard `client.get`, it won't send API Key.
    
    # Let's use the `price-any` endpoint which allows any authenticated user (including session token)
    # or we can mock the API Key dependency.
    
    # For now, let's test `/market/price-any/{ticker_id}`
    response = await client.get(f"/market/price-any/{test_ticker}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["ticker_id"] == test_ticker
    assert data["price"] == 100.0

@pytest.mark.asyncio
async def test_get_portfolio_structure(client: AsyncClient, db_session, test_user, test_ticker):
    """
    Test portfolio response structure and calculations.
    """
    # 1. Add some portfolio assets
    portfolio_item = Portfolio(
        user_id=test_user,
        ticker_id=test_ticker,
        quantity=Decimal("10.0"),
        average_price=Decimal("90.0") # Cost basis = 900
    )
    db_session.add(portfolio_item)
    await db_session.commit()
    
    # Mock current price is 100.0 (from conftest)
    # Valuation = 10 * 100 = 1000
    # Profit = 1000 - 900 = 100
    # Rate = 100 / 900 = 11.11%
    
    response = await client.get("/portfolio")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "assets" in data
    assert len(data["assets"]) == 1
    asset = data["assets"][0]
    
    assert asset["ticker_id"] == test_ticker
    assert asset["quantity"] == 10.0
    assert asset["current_price"] == 100.0
    assert asset["total_value"] == 1000.0
    assert asset["profit_rate"] == 11.11
    
    # Check Total Asset Value
    # Cash (100,000,000) + Stock (1,000) = 100,001,000
    assert float(data["total_asset_value"]) == 100001000.0

@pytest.mark.asyncio
async def test_get_portfolio_empty(client: AsyncClient, test_user):
    """
    Test portfolio response when user has no assets.
    """
    response = await client.get("/portfolio")
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["assets"]) == 0
    # Just cash balance
    assert float(data["total_asset_value"]) == 100000000.0
