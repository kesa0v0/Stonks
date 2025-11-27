from datetime import timedelta, datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import jwt, JWTError, ExpiredSignatureError
from uuid import UUID
from pydantic import ValidationError
import redis

from backend.core.database import get_db
from backend.core import security
from backend.core.config import settings
from backend.models import User
from backend.schemas.token import Token, RefreshTokenRequest, LogoutRequest
from backend.core.cache import get_sync_redis
from backend.core.deps import oauth2_scheme

router = APIRouter(tags=["authentication"])

@router.post("/login/access-token", response_model=Token)
def login_access_token(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    # form_data.username에 email을 담아서 보낸다고 가정
    user = db.query(User).filter(User.email == form_data.username).first()
    
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    return {
        "access_token": security.create_access_token(
            subject=user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
        "refresh_token": security.create_refresh_token(subject=user.id)
    }

@router.post("/login/refresh", response_model=Token)
def refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_sync_redis)
) -> Any:
    """
    Refresh access token using a refresh token
    """
    # Check Blacklist
    if redis_client.exists(f"blacklist:{request.refresh_token}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
        )

    try:
        payload = jwt.decode(
            request.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        
        if user_id is None or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
        
    user = db.query(User).filter(User.id == UUID(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Rotate refresh token (new sliding window)
    return {
        "access_token": security.create_access_token(
            subject=user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
        "refresh_token": security.create_refresh_token(subject=user.id)
    }

@router.post("/logout")
def logout(
    request: LogoutRequest = None,
    token: str = Depends(oauth2_scheme),
    redis_client: redis.Redis = Depends(get_sync_redis)
):
    """
    Logout: Blacklist the access token AND refresh token (if provided).
    """
    # 1. Blacklist Access Token
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        exp = payload.get("exp")
        if exp:
            # Calculate TTL
            ttl = exp - int(datetime.utcnow().timestamp())
            if ttl > 0:
                redis_client.setex(f"blacklist:{token}", ttl, "true")
    except JWTError:
        pass # Already invalid
        
    # 2. Blacklist Refresh Token
    if request and request.refresh_token:
        try:
            payload = jwt.decode(request.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            exp = payload.get("exp")
            if exp:
                ttl = exp - int(datetime.utcnow().timestamp())
                if ttl > 0:
                    redis_client.setex(f"blacklist:{request.refresh_token}", ttl, "true")
        except JWTError:
            pass
            
    return {"message": "Successfully logged out"}