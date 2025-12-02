from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.repository.base import BaseRepository
from backend.models.user import User
from backend.schemas.user import UserCreate, UserUpdate

class UserRepository(BaseRepository[User, UserCreate, UserUpdate]):
    async def get_by_email(self, db: AsyncSession, *, email: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalars().first()

    async def get_by_nickname(self, db: AsyncSession, *, nickname: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.nickname == nickname))
        return result.scalars().first()

    async def is_active(self, user: User) -> bool:
        return user.is_active

    async def get_by_social(self, db: AsyncSession, *, provider: str, social_id: str) -> Optional[User]:
        result = await db.execute(
            select(User).where(User.provider == provider, User.social_id == social_id)
        )
        return result.scalars().first()

user_repo = UserRepository(User)
