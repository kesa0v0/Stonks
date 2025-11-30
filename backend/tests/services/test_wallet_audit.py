import pytest
from decimal import Decimal
from sqlalchemy import select

from backend.models import Wallet, WalletTransactionHistory


@pytest.mark.asyncio
async def test_wallet_balance_update_creates_history(db_session, test_user):
    # Arrange: get wallet for test_user
    result = await db_session.execute(select(Wallet).where(Wallet.user_id == test_user))
    wallet = result.scalars().first()
    assert wallet is not None

    prev_balance = wallet.balance

    # Act: change balance and set reason, then commit
    wallet.last_update_reason = "unit-test:deposit"
    wallet.balance = Decimal(prev_balance) + Decimal("123.45678901")
    db_session.add(wallet)
    await db_session.commit()

    # Assert: a history row was created with correct values
    q = await db_session.execute(
        select(WalletTransactionHistory).where(WalletTransactionHistory.wallet_id == wallet.id)
        .order_by(WalletTransactionHistory.created_at.desc())
    )
    hist = q.scalars().first()
    assert hist is not None
    assert Decimal(hist.prev_balance) == Decimal(prev_balance)
    assert Decimal(hist.new_balance) == Decimal(wallet.balance)
    assert hist.reason == "unit-test:deposit"
