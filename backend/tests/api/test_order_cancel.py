import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal
import uuid

from backend.models import Order, User
from backend.core.enums import OrderStatus, OrderType, OrderSide


@pytest.mark.asyncio
async def test_cancel_pending_order_success(client: AsyncClient, db_session: AsyncSession, test_user, test_ticker):
    """주문 소유자가 PENDING 지정가 주문을 성공적으로 취소할 수 있어야 한다."""
    user_id = test_user
    order_id = uuid.uuid4()

    order = Order(
        id=order_id,
        user_id=user_id,
        ticker_id=test_ticker,
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
        quantity=Decimal("1.0"),
        unfilled_quantity=Decimal("1.0"),
        target_price=Decimal("100.0")
    )
    db_session.add(order)
    await db_session.commit()

    response = await client.post(f"/orders/{order_id}/cancel")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"

    # DB에 반영되었는지 확인
    result = await db_session.execute(select(Order).where(Order.id == order_id))
    db_order = result.scalars().first()
    assert db_order is not None
    assert db_order.status == OrderStatus.CANCELLED
    assert db_order.cancelled_at is not None


@pytest.mark.asyncio
async def test_cancel_order_not_owner_forbidden(client: AsyncClient, db_session: AsyncSession, test_user, test_ticker):
    """다른 사용자의 주문을 취소하려 하면 403이 반환되어야 한다."""
    other_user = uuid.uuid4()
    order_id = uuid.uuid4()

    # Ensure the other user exists to satisfy FK in Postgres
    other = User(
        id=other_user,
        email="other@test.com",
        hashed_password="x",
        nickname="Other",
        is_active=True,
    )
    db_session.add(other)

    order = Order(
        id=order_id,
        user_id=other_user,
        ticker_id=test_ticker,
        side=OrderSide.SELL,
        type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
        quantity=Decimal("2.0"),
        unfilled_quantity=Decimal("2.0"),
        target_price=Decimal("50.0")
    )
    db_session.add(order)
    await db_session.commit()

    response = await client.post(f"/orders/{order_id}/cancel")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cancel_non_pending_order_blocked(client: AsyncClient, db_session: AsyncSession, test_user, test_ticker):
    """이미 FILLED 혹은 CANCELLED 상태인 주문은 취소할 수 없어야 한다."""
    user_id = test_user
    # FILLED 상태
    filled_order_id = uuid.uuid4()
    filled_order = Order(
        id=filled_order_id,
        user_id=user_id,
        ticker_id=test_ticker,
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        status=OrderStatus.FILLED,
        quantity=Decimal("1.0"),
        unfilled_quantity=Decimal("0.0"),
        target_price=Decimal("100.0")
    )
    db_session.add(filled_order)

    # 이미 CANCELLED 상태
    cancelled_order_id = uuid.uuid4()
    cancelled_order = Order(
        id=cancelled_order_id,
        user_id=user_id,
        ticker_id=test_ticker,
        side=OrderSide.SELL,
        type=OrderType.LIMIT,
        status=OrderStatus.CANCELLED,
        quantity=Decimal("1.0"),
        unfilled_quantity=Decimal("1.0"),
        target_price=Decimal("100.0")
    )
    db_session.add(cancelled_order)

    await db_session.commit()

    # FILLED 주문 취소 시도
    resp1 = await client.post(f"/orders/{filled_order_id}/cancel")
    assert resp1.status_code == 400

    # 이미 CANCELLED인 주문 취소 시도
    resp2 = await client.post(f"/orders/{cancelled_order_id}/cancel")
    assert resp2.status_code == 400
