from typing import Optional
from uuid import UUID
from fastapi import Header, HTTPException

# 기본 테스트 유저 ID (하드코딩된 값 대체)
DEFAULT_TEST_USER_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

async def get_current_user_id(x_user_id: Optional[str] = Header(None, alias="x-user-id")) -> UUID:
    """
    헤더에서 x-user-id를 받아와 UUID로 변환하여 반환합니다.
    헤더가 없으면 기본 테스트 유저 ID를 반환합니다.
    """
    if x_user_id:
        try:
            return UUID(x_user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid x-user-id header format")
    
    return UUID(DEFAULT_TEST_USER_ID)