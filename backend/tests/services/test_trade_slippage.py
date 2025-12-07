
import pytest
import uuid
from decimal import Decimal
import json
from sqlalchemy import select
from backend.models import Order
from backend.core.enums import OrderSide, OrderStatus
from backend.services.trade_service import execute_trade
from backend.services.common.price import get_current_price

@pytest.mark.asyncio
async def test_execute_trade_with_slippage(db_session, mock_external_services, test_user, test_ticker):
    """
    Test that execute_trade correctly calculates VWAP using the orderbook (slippage).
    """
    redis_client = mock_external_services["redis"]
    redis_data = mock_external_services["redis_data"]
    ticker_id = test_ticker
    user_id = str(test_user)
    
    # 1. Setup Orderbook in Redis
    # BUY scenario: we consume ASKS
    # Asks: 10 @ 100, 10 @ 110
    # We want to buy 15.
    # 10 units cost 1000
    # 5 units cost 550 (5 * 110)
    # Total cost 1550. VWAP = 1550 / 15 = 103.3333...
    
    ob_data = {
        "asks": [
            {"price": "100", "quantity": "10"},
            {"price": "110", "quantity": "10"}
        ],
        "bids": [
            {"price": "90", "quantity": "10"},
            {"price": "80", "quantity": "10"}
        ]
    }
    redis_data[f"orderbook:{ticker_id}"] = json.dumps(ob_data)
    
    # Also set a current price for fallback (should NOT be used if slippage works)
    price_data = {"ticker_id": ticker_id, "price": "9999.0"}
    redis_data[f"price:{ticker_id}"] = json.dumps(price_data)
    
    # 2. Execute Trade
    order_id = str(uuid.uuid4())
    quantity = 15.0
    
    result = await execute_trade(
        db=db_session,
        redis_client=redis_client,
        user_id=user_id,
        order_id=order_id,
        ticker_id=ticker_id,
        side="BUY",
        quantity=quantity
    )
    
    assert result[0] is True
    
    # 3. Verify Order Price
    stmt = select(Order).where(Order.id == uuid.UUID(order_id))
    order = (await db_session.execute(stmt)).scalars().first()
    
    assert order is not None
    assert order.status == OrderStatus.FILLED
    
    # Expected VWAP: 103.3333...
    expected_price = Decimal("1550") / Decimal("15")
    
    # Allow small rounding difference
    assert abs(order.price - expected_price) < Decimal("0.001")
    assert order.price != Decimal("9999.0") # Should NOT use fallback

@pytest.mark.asyncio
async def test_execute_trade_slippage_insufficient_liquidity_fallback(db_session, mock_external_services, test_user, test_ticker):
    """
    Test fallback to current price when liquidity is insufficient.
    """
    redis_client = mock_external_services["redis"]
    redis_data = mock_external_services["redis_data"]
    ticker_id = test_ticker
    user_id = str(test_user)
    
    # 1. Setup Orderbook with insufficient liquidity (EMPTY to force fallback)
    # Asks: [] (Empty)
    # We want to buy 10.
    ob_data = {
        "asks": [],
        "bids": []
    }
    redis_data[f"orderbook:{ticker_id}"] = json.dumps(ob_data)
    
    # Set fallback price
    fallback_price = "200.0"
    price_data = {"ticker_id": ticker_id, "price": fallback_price}
    redis_data[f"price:{ticker_id}"] = json.dumps(price_data)
    
    # 2. Execute Trade
    order_id = str(uuid.uuid4())
    quantity = 10.0
    
    result = await execute_trade(
        db=db_session,
        redis_client=redis_client,
        user_id=user_id,
        order_id=order_id,
        ticker_id=ticker_id,
        side="BUY",
        quantity=quantity
    )
    
    assert result[0] is True
    
    # 3. Verify Order Price -> Should be fallback price
    stmt = select(Order).where(Order.id == uuid.UUID(order_id))
    order = (await db_session.execute(stmt)).scalars().first()
    
    assert order is not None
    assert order.price == Decimal(fallback_price)

@pytest.mark.asyncio
async def test_execute_trade_sell_slippage(db_session, mock_external_services, test_user, test_ticker):
    """
    Test slippage for SELL orders (using Bids).
    """
    redis_client = mock_external_services["redis"]
    redis_data = mock_external_services["redis_data"]
    ticker_id = test_ticker
    user_id = str(test_user)
    
    # Setup Portfolio so user can sell
    # Ensure user has enough quantity
    from backend.models import Portfolio
    pf = Portfolio(user_id=uuid.UUID(user_id), ticker_id=ticker_id, quantity=Decimal("100"), average_price=Decimal("50"))
    db_session.add(pf)
    await db_session.commit()
    
    # 1. Setup Orderbook
    # Bids: 10 @ 90, 10 @ 80 (Best price first)
    # We sell 15.
    # 10 @ 90 = 900
    # 5 @ 80 = 400
    # Total = 1300
    # VWAP = 1300 / 15 = 86.666...
    
    ob_data = {
        "asks": [],
        "bids": [
            {"price": "90", "quantity": "10"},
            {"price": "80", "quantity": "10"}
        ]
    }
    redis_data[f"orderbook:{ticker_id}"] = json.dumps(ob_data)
    
    # Fallback price
    price_data = {"ticker_id": ticker_id, "price": "1.0"}
    redis_data[f"price:{ticker_id}"] = json.dumps(price_data)
    
    # 2. Execute Trade
    order_id = str(uuid.uuid4())
    quantity = 15.0
    
    result = await execute_trade(
        db=db_session,
        redis_client=redis_client,
        user_id=user_id,
        order_id=order_id,
        ticker_id=ticker_id,
        side="SELL",
        quantity=quantity
    )
    
    assert result[0] is True
    
    # 3. Verify Order Price
    stmt = select(Order).where(Order.id == uuid.UUID(order_id))
    order = (await db_session.execute(stmt)).scalars().first()
    
    expected_price = Decimal("1300") / Decimal("15")
    assert abs(order.price - expected_price) < Decimal("0.001")
