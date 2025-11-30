import pytest
from decimal import Decimal
from backend.core.enums import OrderType, OrderSide, OrderStatus
from backend.models import Order, Wallet, Portfolio
from backend.services.order_service import place_order
from sqlalchemy import select
import uuid

@pytest.mark.asyncio
async def test_stop_loss_order_placement(db_session, mock_external_services, test_user, test_ticker):
    """
    Test placing a STOP_LOSS order.
    """
    redis = mock_external_services["redis"]
    
    # 1. Create Stop-Loss Sell Order
    order_data = type('obj', (object,), {
        "ticker_id": test_ticker,
        "side": OrderSide.SELL,
        "type": OrderType.STOP_LOSS,
        "quantity": Decimal("1.0"),
        "target_price": None,
        "stop_price": Decimal("90.0") # 현재가 100 가정, 90 이하로 떨어지면 손절
    })
    
    # Mock Portfolio (보유량 있어야 매도 주문 가능)
    portfolio = Portfolio(
        user_id=test_user,
        ticker_id=test_ticker,
        quantity=Decimal("10.0"),
        average_price=Decimal("100.0")
    )
    db_session.add(portfolio)
    await db_session.commit()

    result = await place_order(db_session, redis, test_user, order_data)
    
    assert result["status"] == "PENDING"
    assert "Stop-Loss order placed" in result["message"]
    
    # DB Verification
    order_id = uuid.UUID(result["order_id"])
    stmt = select(Order).where(Order.id == order_id)
    order = (await db_session.execute(stmt)).scalars().first()
    
    assert order is not None
    assert order.type == OrderType.STOP_LOSS
    assert order.stop_price == Decimal("90.0")
    assert order.status == OrderStatus.PENDING

@pytest.mark.asyncio
async def test_stop_loss_trigger_logic(db_session, mock_external_services, test_user, test_ticker):
    """
    Test triggering logic for STOP_LOSS orders via limit_matcher logic.
    (Integration test style, simulating limit_matcher query)
    """
    # 1. Setup: Place Pending Stop-Loss Sell Order at 90.0
    order = Order(
        user_id=test_user,
        ticker_id=test_ticker,
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS,
        status=OrderStatus.PENDING,
        quantity=Decimal("1.0"),
        stop_price=Decimal("90.0")
    )
    db_session.add(order)
    
    # Portfolio for Sell
    portfolio = Portfolio(
        user_id=test_user,
        ticker_id=test_ticker,
        quantity=Decimal("10.0"),
        average_price=Decimal("100.0")
    )
    db_session.add(portfolio)
    await db_session.commit()
    
    # 2. Simulate Price Drop to 89.0 (Trigger Condition)
    current_price = 89.0
    
    # Query Logic from limit_matcher.py
    stmt = select(Order).where(
        Order.ticker_id == test_ticker,
        Order.status == OrderStatus.PENDING,
        Order.side == OrderSide.SELL,
        Order.type == OrderType.STOP_LOSS,
        Order.stop_price >= current_price # 90 >= 89 True
    )
    result = await db_session.execute(stmt)
    triggered_orders = result.scalars().all()
    
    assert len(triggered_orders) == 1
    assert triggered_orders[0].id == order.id

    # 3. Simulate Price Stay at 91.0 (No Trigger)
    current_price_high = 91.0
    stmt_high = select(Order).where(
        Order.ticker_id == test_ticker,
        Order.status == OrderStatus.PENDING,
        Order.side == OrderSide.SELL,
        Order.type == OrderType.STOP_LOSS,
        Order.stop_price >= current_price_high # 90 >= 91 False
    )
    result_high = await db_session.execute(stmt_high)
    triggered_orders_high = result_high.scalars().all()
    
    assert len(triggered_orders_high) == 0
