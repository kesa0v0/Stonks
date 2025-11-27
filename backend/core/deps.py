from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError, ExpiredSignatureError
from pydantic import ValidationError
from sqlalchemy.orm import Session
from uuid import UUID
import redis

from backend.core.database import get_db
from backend.models import User
from backend.core.config import settings
from backend.core.cache import get_sync_redis

# OAuth2 스키마 정의 (토큰 발급 URL 지정)
# 프론트엔드에서 로그인 요청을 보낼 주소와 일치해야 함
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login/access-token")

def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
    redis_client: redis.Redis = Depends(get_sync_redis)
) -> User:
    """
    JWT 토큰을 검증하고 해당하는 사용자를 반환합니다.
    """
    # 1. Blacklist 확인 (Redis)
    try:
        if redis_client.exists(f"blacklist:{token}"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except redis.RedisError:
        pass 

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
        
    user = db.query(User).filter(User.id == UUID(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    return user

def get_current_user_id(
    current_user: User = Depends(get_current_user)
) -> UUID:
    """
    User 객체에서 ID만 추출하여 반환 (기존 코드 호환성 유지)
    """
    return current_user.id
