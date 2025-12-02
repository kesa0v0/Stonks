from typing import List
from uuid import UUID
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.wallet_transaction_history import WalletTransactionHistory
from backend.repository.base import BaseRepository
from backend.schemas.wallet import WalletTransactionHistoryCreate, WalletTransactionHistoryUpdate

class WalletTransactionHistoryRepository(BaseRepository[WalletTransactionHistory, WalletTransactionHistoryCreate, WalletTransactionHistoryUpdate]):
    async def get_multi_by_user_id(
        self, db: AsyncSession, *, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[WalletTransactionHistory]:
        result = await db.execute(
            select(self.model)
            .where(self.model.user_id == user_id)
            .order_by(desc(self.model.created_at))
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

wallet_transaction_history_repo = WalletTransactionHistoryRepository(WalletTransactionHistory)
