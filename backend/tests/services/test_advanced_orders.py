import pytest
from decimal import Decimal
from backend.core.enums import OrderType, OrderSide, OrderStatus
from backend.models import Order, Wallet, Portfolio
from backend.services.order_service import place_order
from sqlalchemy import select
import uuid

@pytest.mark.asyncio
async def test_take_profit_order(db_session, mock_external_services, test_user, test_ticker):
    """
    Test TAKE_PROFIT order placement and validation.
    """
    redis = mock_external_services["redis"]
    
    # 1. Create Take-Profit Sell Order (Long position close)
    # Current price 100, Target 110. (Take Profit is Trigger Market if Price >= 110)
    order_data = type('obj', (object,), {
        "ticker_id": test_ticker,
        "side": OrderSide.SELL,
        "type": OrderType.TAKE_PROFIT,
        "quantity": Decimal("1.0"),
        "target_price": None,
        "stop_price": Decimal("110.0"),
        "trailing_gap": None
    })
    
    # Portfolio needed
    portfolio = Portfolio(user_id=test_user, ticker_id=test_ticker, quantity=Decimal("10.0"), average_price=Decimal("100.0"))
    db_session.add(portfolio)
    await db_session.commit()

    result = await place_order(db_session, redis, test_user, order_data)
    assert result["status"] == "PENDING"
    
    # Verify DB
    order_id = uuid.UUID(result["order_id"])
    stmt = select(Order).where(Order.id == order_id)
    order = (await db_session.execute(stmt)).scalars().first()
    assert order.type == OrderType.TAKE_PROFIT
    assert order.stop_price == Decimal("110.0")

@pytest.mark.asyncio
async def test_stop_limit_order(db_session, mock_external_services, test_user, test_ticker):
    """
    Test STOP_LIMIT order placement.
    """
    redis = mock_external_services["redis"]
    
    # Stop Sell: Trigger at 90, Limit at 89
    order_data = type('obj', (object,), {
        "ticker_id": test_ticker,
        "side": OrderSide.SELL,
        "type": OrderType.STOP_LIMIT,
        "quantity": Decimal("1.0"),
        "target_price": Decimal("89.0"),
        "stop_price": Decimal("90.0"),
        "trailing_gap": None
    })
    
    # Portfolio needed
    portfolio = Portfolio(user_id=test_user, ticker_id=test_ticker, quantity=Decimal("10.0"), average_price=Decimal("100.0"))
    db_session.add(portfolio)
    await db_session.commit()

    result = await place_order(db_session, redis, test_user, order_data)
    assert result["status"] == "PENDING"
    
    # Verify DB
    order_id = uuid.UUID(result["order_id"])
    stmt = select(Order).where(Order.id == order_id)
    order = (await db_session.execute(stmt)).scalars().first()
    assert order.type == OrderType.STOP_LIMIT
    assert order.stop_price == Decimal("90.0")
    assert order.target_price == Decimal("89.0")

@pytest.mark.asyncio
async def test_trailing_stop_order(db_session, mock_external_services, test_user, test_ticker):
    """
    Test TRAILING_STOP order placement.
    """
    redis = mock_external_services["redis"]
    
    # Trailing Sell: Gap 5.0. Current Price 100. Initial Stop = 95.
    order_data = type('obj', (object,), {
        "ticker_id": test_ticker,
        "side": OrderSide.SELL,
        "type": OrderType.TRAILING_STOP,
        "quantity": Decimal("1.0"),
        "target_price": None,
        "stop_price": None,
        "trailing_gap": Decimal("5.0")
    })
    
    # Portfolio needed
    portfolio = Portfolio(user_id=test_user, ticker_id=test_ticker, quantity=Decimal("10.0"), average_price=Decimal("100.0"))
    db_session.add(portfolio)
    await db_session.commit()

    result = await place_order(db_session, redis, test_user, order_data)
    assert result["status"] == "PENDING"
    
    # Verify DB
    order_id = uuid.UUID(result["order_id"])
    stmt = select(Order).where(Order.id == order_id)
    order = (await db_session.execute(stmt)).scalars().first()
    assert order.type == OrderType.TRAILING_STOP
    assert order.trailing_gap == Decimal("5.0")
    # Initial stop price should be set (Current 100 - 5 = 95)
    # Note: place_order logic sets stop_price based on current_price from redis mock
    # Our mock redis returns 100.0 for price:TEST-COIN
    assert order.stop_price == Decimal("95.0")
