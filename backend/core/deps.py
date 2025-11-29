from typing import Optional
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError, ExpiredSignatureError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import redis.asyncio as async_redis 

from backend.core.database import get_db
from backend.repository.user import user_repo
from backend.models import User, ApiKey
from datetime import datetime
from sqlalchemy import update
from backend.core import security
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
    user = await user_repo.get(db, id=UUID(user_id))
    
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

async def get_current_user_by_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
    redis_client: async_redis.Redis = Depends(get_redis)
) -> User:
    """Strict API Key auth: missing key => 401. Includes rate limit and last_used_at update."""
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API Key")
    prefix = x_api_key[:12]
    result = await db.execute(select(ApiKey).where(ApiKey.key_prefix == prefix, ApiKey.is_active == True))
    candidates = result.scalars().all()
    if not candidates:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")
    for candidate in candidates:
        if security.verify_api_key(x_api_key, candidate.hashed_key):
            # Rate limit: fixed window per minute
            window = datetime.utcnow().strftime("%Y%m%d%H%M")
            rl_key = f"rl:apikey:{candidate.id}:{window}"
            try:
                current = await redis_client.incr(rl_key)
                if current == 1:
                    await redis_client.expire(rl_key, 61)
                limit = settings.API_KEY_RATE_LIMIT_PER_MINUTE
                if current > limit:
                    raise HTTPException(status_code=429, detail="API Key rate limit exceeded")
            except HTTPException:
                raise
            except Exception:
                pass

            try:
                await db.execute(
                    update(ApiKey).where(ApiKey.id == candidate.id).values(last_used_at=datetime.utcnow())
                )
                await db.commit()
            except Exception:
                pass

            user_result = await db.execute(select(User).where(User.id == candidate.user_id))
            user = user_result.scalars().first()
            if not user or not user.is_active:
                raise HTTPException(status_code=401, detail="Inactive user")
            return user
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")

async def get_current_user_any(
    bearer_user: Optional[User] = Depends(get_current_user),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
    redis_client: async_redis.Redis = Depends(get_redis)
) -> User:
    if bearer_user:
        return bearer_user
    if x_api_key:
        # call helper directly (strict); convert 401 Missing to unified message
        try:
            return await get_current_user_by_api_key(x_api_key=x_api_key, db=db, redis_client=redis_client)
        except HTTPException as e:
            if e.status_code == status.HTTP_401_UNAUTHORIZED:
                raise HTTPException(status_code=401, detail="Invalid API Key")
            raise
    raise HTTPException(status_code=401, detail="Authentication required (Bearer or X-API-Key)")