from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError, ExpiredSignatureError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import redis.asyncio as async_redis 

from backend.core.database import get_db
from backend.models import User
from backend.core.config import settings
from backend.core.cache import get_redis 

# OAuth2 스키마 정의 (토큰 발급 URL 지정)
# 프론트엔드에서 로그인 요청을 보낼 주소와 일치해야 함
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login/access-token")

async def get_current_user( 
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
    redis_client: async_redis.Redis = Depends(get_redis) 
) -> User:
    """
    JWT 토큰을 검증하고 해당하는 사용자를 반환합니다.
    """
    # 1. Blacklist 확인 (Redis) - 비동기 Redis 사용
    try:
        if await redis_client.exists(f"blacklist:{token}"): # Use await
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except async_redis.RedisError as e: 
        print(f"DEBUG: RedisError caught in deps: {e}") # DEBUG PRINT
        pass 
    except Exception as e:
        # HTTPException은 여기서 잡히면 안됨 (위에서 raise한 것)
        if isinstance(e, HTTPException):
            raise e
        print(f"DEBUG: Unexpected Error in deps: {e}") # DEBUG PRINT
        raise e

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        
        if user_id is None or token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 비동기 쿼리로 변경
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    return user

async def get_current_user_id(
    current_user: User = Depends(get_current_user)
) -> UUID:
    """
    User 객체에서 ID만 추출하여 반환 (기존 코드 호환성 유지)
    """
    return current_user.id

async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    관리자 권한을 가진 사용자만 반환합니다.
    """
    if current_user.email != settings.ADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user