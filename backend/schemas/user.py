from typing import Optional, List, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict, EmailStr
from backend.schemas.common import DecimalStr
from backend.models import Ticker, User

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    nickname: str

class UserUpdate(BaseModel):
    password: Optional[str] = None
    nickname: Optional[str] = None
    is_active: Optional[bool] = None

class UserResponse(BaseModel):
    id: UUID
    email: str
    nickname: str
    is_active: bool
    badges: List[Dict[str, Any]]
    is_bankrupt: Optional[bool] = False
    dividend_rate: Optional[DecimalStr] = "0.5"
    is_listed: Optional[bool] = False
    
    model_config = ConfigDict(from_attributes=True)

class UserProfileResponse(BaseModel):
    id: UUID
    nickname: str
    badges: List[Dict[str, Any]]
    profit_rate: Optional[DecimalStr] = None # 공개 여부에 따라 달라짐
    
    model_config = ConfigDict(from_attributes=True)


async def to_user_response(user: User, db: AsyncSession) -> UserResponse:
    """Build UserResponse with an explicit is_listed flag derived from ticker state."""
    ticker_id = f"HUMAN-{user.id}"
    stmt = select(Ticker).where(Ticker.id == ticker_id, Ticker.is_active == True)
    result = await db.execute(stmt)
    ticker = result.scalars().first()

    base = UserResponse.model_validate(user, from_attributes=True)
    return base.model_copy(update={"is_listed": bool(ticker)})
