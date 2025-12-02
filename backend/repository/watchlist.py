from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from backend.models.watchlist import Watchlist

class WatchlistRepository:
    async def get_by_user(self, db: AsyncSession, user_id: UUID) -> List[Watchlist]:
        result = await db.execute(
            select(Watchlist)
            .options(joinedload(Watchlist.ticker))
            .where(Watchlist.user_id == user_id)
        )
        return result.scalars().all()

    async def create(self, db: AsyncSession, user_id: UUID, ticker_id: str) -> Watchlist:
        db_obj = Watchlist(user_id=user_id, ticker_id=ticker_id)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def get_by_user_and_ticker(self, db: AsyncSession, user_id: UUID, ticker_id: str) -> Optional[Watchlist]:
        result = await db.execute(
            select(Watchlist)
            .where(Watchlist.user_id == user_id, Watchlist.ticker_id == ticker_id)
        )
        return result.scalars().first()

    async def delete(self, db: AsyncSession, user_id: UUID, ticker_id: str) -> bool:
        result = await db.execute(
            select(Watchlist)
            .where(Watchlist.user_id == user_id, Watchlist.ticker_id == ticker_id)
        )
        obj = result.scalars().first()
        if obj:
            await db.delete(obj)
            await db.commit()
            return True
        return False

watchlist_repo = WatchlistRepository()
