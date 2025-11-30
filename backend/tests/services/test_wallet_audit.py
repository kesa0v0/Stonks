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


@pytest.mark.asyncio
async def test_no_history_when_balance_unchanged(db_session, test_user):
    # Arrange
    result = await db_session.execute(select(Wallet).where(Wallet.user_id == test_user))
    wallet = result.scalars().first()

    # Act: update without changing balance
    wallet.last_update_reason = "unit-test:no-balance-change"
    db_session.add(wallet)
    await db_session.commit()

    # Assert: no new history rows for this wallet
    q = await db_session.execute(
        select(WalletTransactionHistory).where(WalletTransactionHistory.wallet_id == wallet.id)
    )
    rows = q.scalars().all()
    # From previous tests there could be existing rows in shared session scope,
    # so we check that none of them have the current reason label
    assert all(h.reason != "unit-test:no-balance-change" for h in rows)


@pytest.mark.asyncio
async def test_multiple_updates_create_multiple_history_rows(db_session, test_user):
    result = await db_session.execute(select(Wallet).where(Wallet.user_id == test_user))
    wallet = result.scalars().first()

    # Baseline count
    q0 = await db_session.execute(select(WalletTransactionHistory).where(WalletTransactionHistory.wallet_id == wallet.id))
    before_count = len(q0.scalars().all())

    # First change
    wallet.last_update_reason = "unit-test:step1"
    wallet.balance = (wallet.balance or 0) + Decimal("1.0")
    db_session.add(wallet)
    await db_session.commit()

    # Second change
    wallet.last_update_reason = "unit-test:step2"
    wallet.balance = wallet.balance + Decimal("2.0")
    db_session.add(wallet)
    await db_session.commit()

    q1 = await db_session.execute(select(WalletTransactionHistory).where(WalletTransactionHistory.wallet_id == wallet.id))
    after_rows = q1.scalars().all()
    assert len(after_rows) >= before_count + 2
    reasons = [h.reason for h in after_rows]
    assert "unit-test:step1" in reasons
    assert "unit-test:step2" in reasons


@pytest.mark.asyncio
async def test_history_reason_can_be_null(db_session, test_user):
    result = await db_session.execute(select(Wallet).where(Wallet.user_id == test_user))
    wallet = result.scalars().first()

    # Do not set last_update_reason, ensure hook still writes
    wallet.last_update_reason = None
    prev = wallet.balance
    wallet.balance = (prev or 0) + Decimal("0.5")
    db_session.add(wallet)
    await db_session.commit()

    q = await db_session.execute(
        select(WalletTransactionHistory)
        .where(WalletTransactionHistory.wallet_id == wallet.id)
        .order_by(WalletTransactionHistory.created_at.desc())
    )
    hist = q.scalars().first()
    assert hist is not None
    assert Decimal(hist.prev_balance) == Decimal(prev)
    assert Decimal(hist.new_balance) == Decimal(wallet.balance)
    # reason is nullable
    assert hist.reason is None
