import pytest
from decimal import Decimal
from sqlalchemy import select

from backend.models import Wallet, WalletTransactionHistory
from backend.services.common.wallet import add_balance
from backend.core.constants import WALLET_REASON_ADJUSTMENT


@pytest.mark.asyncio
async def test_history_not_persisted_on_rollback(db_session, test_user):
    # Arrange
    wallet = (await db_session.execute(select(Wallet).where(Wallet.user_id == test_user))).scalars().first()
    assert wallet is not None
    wallet_id = wallet.id

    # Baseline count
    before = (await db_session.execute(select(WalletTransactionHistory).where(WalletTransactionHistory.wallet_id == wallet_id))).scalars().all()
    before_count = len(before)

    # Act within implicit transaction and rollback
    add_balance(wallet, Decimal("7.77"), WALLET_REASON_ADJUSTMENT)
    await db_session.flush()
    await db_session.rollback()

    # Assert: no new history rows persisted
    after = (await db_session.execute(select(WalletTransactionHistory).where(WalletTransactionHistory.wallet_id == wallet_id))).scalars().all()
    assert len(after) == before_count


@pytest.mark.asyncio
async def test_history_persisted_on_commit(db_session, test_user):
    wallet = (await db_session.execute(select(Wallet).where(Wallet.user_id == test_user))).scalars().first()
    assert wallet is not None

    add_balance(wallet, Decimal("3.33"), WALLET_REASON_ADJUSTMENT)
    await db_session.commit()

    rows = (await db_session.execute(select(WalletTransactionHistory).where(WalletTransactionHistory.wallet_id == wallet.id))).scalars().all()
    assert any(h.reason == WALLET_REASON_ADJUSTMENT for h in rows)
