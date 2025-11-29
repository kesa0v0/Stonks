import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import Order, Portfolio, Wallet, Ticker, User
from backend.core.enums import OrderSide, OrderStatus, OrderType
from backend.services.trade_service import execute_trade
from backend.schemas.portfolio import PnLResponse

@pytest.mark.asyncio
async def test_pnl_calculation_long_close(db_session: AsyncSession, mock_external_services, test_user, test_ticker):
    """
    Test PnL calculation when closing a long position.
    Scenario: Buy 10 @ 100 -> Sell 5 @ 120 -> PnL should be (120-100)*5 - fees
    """
    redis_client = mock_external_services["redis"]
    
    # 1. Setup User & Wallet
    user_id = test_user
    ticker_id = test_ticker
    
    # Mock Redis Prices
    mock_external_services["redis_data"][f"price:{ticker_id}"] = b'{"price": "100.0"}'
    mock_external_services["redis_data"]["config:trading_fee_rate"] = b"0.001" # 0.1% fee

    # 2. Execute Buy Order (Open Long)
    # Buy 10 units @ 100.0
    buy_order_id = str(uuid.uuid4())
    buy_qty = 10.0
    
    success = await execute_trade(
        db=db_session,
        redis_client=redis_client,
        user_id=str(user_id),
        order_id=buy_order_id,
        ticker_id=ticker_id,
        side=OrderSide.BUY.value,
        quantity=buy_qty
    )
    assert success is True
    
    # Verify Portfolio
    result = await db_session.execute(select(Portfolio).where(Portfolio.user_id == user_id))
    portfolio = result.scalars().first()
    assert float(portfolio.quantity) == 10.0
    assert float(portfolio.average_price) > 100.0 # Price + Fee included in avg price for long

    # 3. Execute Sell Order (Close Long - Partial)
    # Sell 5 units @ 120.0
    mock_external_services["redis_data"][f"price:{ticker_id}"] = b'{"price": "120.0"}'
    sell_order_id = str(uuid.uuid4())
    sell_qty = 5.0
    
    success = await execute_trade(
        db=db_session,
        redis_client=redis_client,
        user_id=str(user_id),
        order_id=sell_order_id,
        ticker_id=ticker_id,
        side=OrderSide.SELL.value,
        quantity=sell_qty
    )
    assert success is True
    
    # 4. Verify Order Realized PnL
    result = await db_session.execute(select(Order).where(Order.id == uuid.UUID(sell_order_id)))
    sell_order = result.scalars().first()
    
    assert sell_order.status == OrderStatus.FILLED
    assert sell_order.realized_pnl is not None
    
    # Manual Calculation
    # Buy Cost Basis (per unit): 100 + (100 * 0.001) = 100.1
    # Portfolio Avg Price should be 100.1
    avg_price = float(portfolio.average_price)
    assert abs(avg_price - 100.1) < 0.0001
    
    # Sell Revenue: 120 * 5 = 600
    # Sell Fee: 600 * 0.001 = 0.6
    # Net Income: 599.4 (Wallet balance increase)
    
    # Realized PnL Logic: (Sell Price - Avg Buy Price) * Qty - Sell Fee (Allocated)
    # (120 - 100.1) * 5 - 0.6 = 19.9 * 5 - 0.6 = 99.5 - 0.6 = 98.9
    
    expected_pnl = (120.0 - avg_price) * sell_qty - (120.0 * sell_qty * 0.001)
    
    assert float(sell_order.realized_pnl) == pytest.approx(expected_pnl, abs=0.0001)
    
@pytest.mark.asyncio
async def test_get_my_pnl_api(client, db_session, test_user, test_ticker):
    """
    Test GET /me/pnl API
    """
    user_id = test_user
    ticker_id = test_ticker
    
    # 1. Create Orders with PnL manually (to skip trade execution complexity)
    today = datetime.now(timezone.utc)
    
    order1 = Order(
        user_id=user_id,
        ticker_id=ticker_id,
        side=OrderSide.SELL,
        status=OrderStatus.FILLED,
        type=OrderType.MARKET,
        quantity=5,
        price=120,
        filled_at=today,
        realized_pnl=100.0 # Profit 100
    )
    
    order2 = Order(
        user_id=user_id,
        ticker_id=ticker_id,
        side=OrderSide.SELL,
        status=OrderStatus.FILLED,
        type=OrderType.MARKET,
        quantity=5,
        price=90,
        filled_at=today,
        realized_pnl=-50.0 # Loss 50
    )
    
    # Order outside date range
    past_date = today - timedelta(days=10)
    order3 = Order(
        user_id=user_id,
        ticker_id=ticker_id,
        side=OrderSide.SELL,
        status=OrderStatus.FILLED,
        type=OrderType.MARKET,
        quantity=5,
        price=110,
        filled_at=past_date,
        realized_pnl=200.0 # Should not be included
    )
    
    db_session.add_all([order1, order2, order3])
    await db_session.commit()
    
    # 2. Call API
    start_date = today.strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
    
    response = await client.get(f"/me/pnl?start={start_date}&end={end_date}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["start_date"] == start_date
    assert data["end_date"] == end_date
    assert data["realized_pnl"] == 50.0 # 100 - 50 = 50
