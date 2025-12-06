import pytest
import uuid
from decimal import Decimal
from httpx import AsyncClient
from backend.models import Order, User, Ticker
from backend.core.enums import OrderSide, OrderStatus, OrderType

@pytest.mark.asyncio
async def test_get_orderbook(client: AsyncClient, db_session, test_ticker, test_user):
    """
    Test retrieving orderbook with aggregated limit orders.
    """
    ticker_id = test_ticker
    user_id = test_user
    
    # 1. Create Limit Orders (Pending)
    orders = [
        # Bids (Buy) - High to Low
        Order(
            id=uuid.uuid4(), user_id=user_id, ticker_id=ticker_id,
            side=OrderSide.BUY, type=OrderType.LIMIT, status=OrderStatus.PENDING,
                            target_price=Decimal("100.0"), quantity=Decimal("10.0"), unfilled_quantity=Decimal("10.0")        ),
        Order(
            id=uuid.uuid4(), user_id=user_id, ticker_id=ticker_id,
            side=OrderSide.BUY, type=OrderType.LIMIT, status=OrderStatus.PENDING,
                            target_price=Decimal("100.0"), quantity=Decimal("5.0"), unfilled_quantity=Decimal("5.0")        ),
        Order(
            id=uuid.uuid4(), user_id=user_id, ticker_id=ticker_id,
            side=OrderSide.BUY, type=OrderType.LIMIT, status=OrderStatus.PENDING,
                            target_price=Decimal("99.0"), quantity=Decimal("20.0"), unfilled_quantity=Decimal("20.0")        ),
        
        # Asks (Sell) - Low to High
        Order(
            id=uuid.uuid4(), user_id=user_id, ticker_id=ticker_id,
            side=OrderSide.SELL, type=OrderType.LIMIT, status=OrderStatus.PENDING,
                            target_price=Decimal("101.0"), quantity=Decimal("8.0"), unfilled_quantity=Decimal("8.0")        ),
        Order(
            id=uuid.uuid4(), user_id=user_id, ticker_id=ticker_id,
            side=OrderSide.SELL, type=OrderType.LIMIT, status=OrderStatus.PENDING,
                            target_price=Decimal("102.0"), quantity=Decimal("15.0"), unfilled_quantity=Decimal("15.0")        ),
    ]
    
    db_session.add_all(orders)
    await db_session.commit()
    
    # 2. Call API
    response = await client.get(f"/api/v1/market/orderbook/{ticker_id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["ticker_id"] == ticker_id
    
    # 3. Verify Bids
    # Expect: 100.0 (qty 15), 99.0 (qty 20)
    bids = data["bids"]
    assert len(bids) == 2
    assert float(bids[0]["price"]) == 100.0
    assert float(bids[0]["quantity"]) == 15.0
    assert float(bids[1]["price"]) == 99.0
    assert float(bids[1]["quantity"]) == 20.0
    
    # 4. Verify Asks
    # Expect: 101.0 (qty 8), 102.0 (qty 15)
    asks = data["asks"]
    assert len(asks) == 2
    assert float(asks[0]["price"]) == 101.0
    assert float(asks[0]["quantity"]) == 8.0
    assert float(asks[1]["price"]) == 102.0
    assert float(asks[1]["quantity"]) == 15.0

@pytest.mark.asyncio
async def test_get_orderbook_empty(client: AsyncClient, test_ticker):
    """
    Test empty orderbook.
    """
    response = await client.get(f"/api/v1/market/orderbook/{test_ticker}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["ticker_id"] == test_ticker
    assert data["bids"] == []
    assert data["asks"] == []
