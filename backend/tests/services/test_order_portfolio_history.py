import pytest
from uuid import UUID
from sqlalchemy import select
from decimal import Decimal

from backend.models import Order, OrderStatus, Portfolio, OrderStatusHistory, PortfolioHistory
from backend.core.enums import OrderType, OrderSide
from backend.services.order_service import place_order, cancel_order_logic


@pytest.mark.asyncio
async def test_order_status_history_on_insert_and_cancel(db_session, test_user, test_ticker, mock_external_services):
    user_id = UUID(str(test_user))

    # Place a LIMIT order (goes to DB as PENDING)
    from backend.schemas.order import OrderCreate
    order_in = OrderCreate(
        ticker_id=test_ticker,
        side=OrderSide.BUY,
        quantity=Decimal("1.0"),
        type=OrderType.LIMIT,
        target_price=Decimal("10.0"),
    )

    res = await place_order(db_session, mock_external_services["redis"], user_id, order_in)
    order_id = UUID(res["order_id"])

    # Verify history for insert
    rows = (await db_session.execute(select(OrderStatusHistory).where(OrderStatusHistory.order_id == order_id))).scalars().all()
    assert any(h.new_status == OrderStatus.PENDING for h in rows)

    # Cancel the order -> status should become CANCELLED and history recorded
    await cancel_order_logic(db_session, user_id, order_id)
    rows2 = (await db_session.execute(select(OrderStatusHistory).where(OrderStatusHistory.order_id == order_id))).scalars().all()
    assert any(h.new_status == OrderStatus.CANCELLED for h in rows2)


@pytest.mark.asyncio
async def test_portfolio_history_insert_update_delete(db_session, test_user, test_ticker):
    # Insert
    p = Portfolio(user_id=test_user, ticker_id=test_ticker, quantity=Decimal("1.0"), average_price=Decimal("100.0"))
    db_session.add(p)
    await db_session.commit()

    rows_ins = (await db_session.execute(select(PortfolioHistory).where(PortfolioHistory.user_id == test_user))).scalars().all()
    assert any(r.action == "insert" and r.ticker_id == test_ticker for r in rows_ins)

    # Update
    p.quantity = Decimal("2.0")
    p.average_price = Decimal("120.0")
    await db_session.commit()

    rows_upd = (await db_session.execute(select(PortfolioHistory).where(PortfolioHistory.user_id == test_user))).scalars().all()
    assert any(r.action == "update" and r.new_quantity == Decimal("2.0") for r in rows_upd)

    # Delete
    await db_session.delete(p)
    await db_session.commit()

    rows_del = (await db_session.execute(select(PortfolioHistory).where(PortfolioHistory.user_id == test_user))).scalars().all()
    assert any(r.action == "delete" and r.ticker_id == test_ticker for r in rows_del)
