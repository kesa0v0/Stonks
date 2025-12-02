from uuid import UUID
from fastapi import APIRouter, Depends
from backend.core.rate_limit_config import get_rate_limiter
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.schemas.user import UserProfileResponse
from backend.services.user_service import get_user_profile

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/{user_id}/profile", response_model=UserProfileResponse, dependencies=[Depends(get_rate_limiter("/users/{user_id}/profile"))])
async def get_user_profile_endpoint(
    user_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    특정 유저의 프로필 정보를 조회합니다. (닉네임, 뱃지, 수익률)
    """
    return await get_user_profile(db, user_id)
