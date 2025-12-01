import pytest
from httpx import AsyncClient
from backend.models import Order, User, Wallet
from backend.core.enums import OrderType, OrderSide, OrderStatus
from backend.core.security import create_access_token
import uuid
from decimal import Decimal

@pytest.mark.asyncio
async def test_order_cancellation_isolation(client: AsyncClient, db_session, test_user, another_user_token, test_ticker):
    """
    Scenario: User B tries to cancel User A's order.
    Expected: 403 Forbidden or 404 Not Found.
    """
    # 1. Create an order for User A (test_user)
    order_id = uuid.uuid4()
    order = Order(
        id=order_id,
        user_id=test_user,
        ticker_id=test_ticker, # Use the ticker_id from the fixture
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
        quantity=Decimal("10.0"),
        unfilled_quantity=Decimal("10.0"),
        target_price=Decimal("100.0"),
        price=None
    )
    db_session.add(order)
    await db_session.commit()

    # 2. User B tries to cancel User A's order
    headers = {"Authorization": f"Bearer {another_user_token}"}
    response = await client.post(f"/api/v1/orders/{order_id}/cancel", headers=headers)

    # 3. Expect Failure
    assert response.status_code in [403, 404]
    if response.status_code == 403:
        assert "권한이 없습니다" in response.json()["detail"]

@pytest.mark.asyncio
async def test_order_detail_isolation(client: AsyncClient, db_session, test_user, another_user_token, test_ticker):
    """
    Scenario: User B tries to view User A's order details.
    Expected: 403 Forbidden or 404 Not Found.
    """
    # 1. Create an order for User A
    order_id = uuid.uuid4()
    order = Order(
        id=order_id,
        user_id=test_user,
        ticker_id=test_ticker, # Use the ticker_id from the fixture
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        status=OrderStatus.FILLED,
        quantity=Decimal("5.0"),
        unfilled_quantity=Decimal("0.0"),
        target_price=None,
        price=Decimal("200.0")
    )
    db_session.add(order)
    await db_session.commit()

    # 2. User B tries to access User A's order
    headers = {"Authorization": f"Bearer {another_user_token}"}
    response = await client.get(f"/api/v1/orders/{order_id}", headers=headers)

    # 3. Expect Failure
    assert response.status_code in [403, 404]

@pytest.mark.asyncio
async def test_portfolio_isolation(client: AsyncClient, db_session, test_user, another_user_token):
    """
    Scenario: User B tries to access portfolio.
    Since /me/portfolio endpoint relies on the JWT token to determine the user ID,
    User B should only see their OWN portfolio, not User A's.
    So we verify that User B sees an empty/different portfolio, proving isolation by design.
    """
    # 1. User A has 100,000,000 KRW (set in conftest)
    
    # 2. User B (another_user) has 500,000 KRW (set in conftest)
    headers = {"Authorization": f"Bearer {another_user_token}"}
    response = await client.get("/api/v1/me/portfolio", headers=headers) # Changed from /portfolio
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify it's User B's data
    assert float(data["cash_balance"]) == 500000.0
    # User A had 100,000,000, so if we saw that, it would be a fail.
    assert float(data["cash_balance"]) != 100000000.0 # This assertion is redundant given the above
