import pytest
from httpx import AsyncClient
from uuid import UUID
from datetime import datetime, timezone, timedelta
from backend.models import User, Order, Ticker # Added Ticker import
from backend.core.enums import OrderStatus
from backend.schemas.user import UserProfileResponse

@pytest.mark.asyncio
async def test_get_user_profile_success(client: AsyncClient, db_session, test_user: UUID):
    """
    Test retrieving a user's profile successfully.
    """
    # 1. Prepare test user with badges
    user = await db_session.get(User, test_user)
    assert user is not None
    user.nickname = "TestUser"
    user.badges = [
        {"title": "Early Bird", "date": "2023-01-01"},
        {"title": "Season 1 Winner", "date": "2023-12-31"}
    ]
    # Set created_at for PnL calculation
    user.created_at = datetime.now(timezone.utc) - timedelta(days=100)
    db_session.add(user)

    # Add required tickers for orders
    ticker1 = Ticker(id="TEST_TICKER_1", symbol="TT1", name="Test Ticker One", market_type="CRYPTO", currency="KRW")
    ticker2 = Ticker(id="TEST_TICKER_2", symbol="TT2", name="Test Ticker Two", market_type="CRYPTO", currency="KRW")
    db_session.add_all([ticker1, ticker2])

    # 2. Simulate some trades to generate PnL
    # Realized PnL: 100 + 50 = 150
    order1 = Order(
        user_id=test_user,
        ticker_id="TEST_TICKER_1",
        side="BUY", type="MARKET", quantity=10,
        status=OrderStatus.FILLED, filled_at=datetime.now(timezone.utc) - timedelta(days=50),
        realized_pnl=100.00
    )
    order2 = Order(
        user_id=test_user,
        ticker_id="TEST_TICKER_2",
        side="SELL", type="MARKET", quantity=5,
        status=OrderStatus.FILLED, filled_at=datetime.now(timezone.utc) - timedelta(days=20),
        realized_pnl=50.00
    )
    db_session.add_all([order1, order2])
    await db_session.commit()
    await db_session.refresh(user) # Refresh user to get latest data including created_at

    response = await client.get(f"/api/v1/users/{test_user}/profile")

    # 4. Assert the response
    assert response.status_code == 200
    profile_data = response.json()

    # Validate with Pydantic schema
    UserProfileResponse(**profile_data)

    assert profile_data["id"] == str(test_user)
    assert profile_data["nickname"] == "TestUser"
    assert len(profile_data["badges"]) == 2
    assert profile_data["badges"][0]["title"] == "Early Bird"
    
    # Check profit_rate calculation (Realized PnL: 150, Initial Capital: 1,000,000)
    # profit_rate = (150 / 1,000,000) * 100 = 0.015%
    assert profile_data["profit_rate"] == "0.02" # Formatted to two decimal places, rounded up

@pytest.mark.asyncio
async def test_get_user_profile_no_badges_no_pnl(client: AsyncClient, db_session, test_user: UUID):
    """
    Test user profile for a user with no badges and no PnL.
    """
    user = await db_session.get(User, test_user)
    assert user is not None
    user.nickname = "NoBadgeUser"
    user.badges = []
    user.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    response = await client.get(f"/api/v1/users/{test_user}/profile")
    assert response.status_code == 200
    profile_data = response.json()

    assert profile_data["id"] == str(test_user)
    assert profile_data["nickname"] == "NoBadgeUser"
    assert profile_data["badges"] == []
    assert profile_data["profit_rate"] == "0.00" # Should be 0.00 if no PnL

@pytest.mark.asyncio
async def test_get_user_profile_non_existent(client: AsyncClient):
    """
    Test retrieving profile for a non-existent user.
    """
    non_existent_uuid = UUID("12345678-1234-5678-1234-567812345678")
    response = await client.get(f"/api/v1/users/{non_existent_uuid}/profile")
    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]
