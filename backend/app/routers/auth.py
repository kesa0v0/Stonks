from datetime import timedelta, datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError, ExpiredSignatureError
from uuid import UUID
from pydantic import ValidationError
import redis.asyncio as async_redis # Use async_redis
import json
import uuid

from backend.core.database import get_db
from backend.core import security
from backend.core.config import settings
from backend.models import User
from backend.schemas.token import Token, RefreshTokenRequest, LogoutRequest
from backend.schemas.user import UserResponse # Import the new UserResponse schema
from backend.core.cache import get_redis # Import async get_redis
from backend.core.deps import oauth2_scheme, get_current_user

router = APIRouter(tags=["authentication"])

@router.get("/login/me", response_model=UserResponse)
async def read_current_user_me(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user's information.
    """
    return current_user

@router.post("/login/access-token", response_model=Token)
async def login_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    redis_client: async_redis.Redis = Depends(get_redis)
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalars().first()
    
    # Check if user exists and has a password (local user)
    if not user or not user.hashed_password or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Generate refresh token with JTI and persist JTI in Redis for reuse detection
    refresh_jti = str(uuid.uuid4())
    refresh_token = security.create_refresh_token(subject=user.id, jti=refresh_jti)

    # Store current valid refresh token state: {jti, exp}
    refresh_exp = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    ttl = int(refresh_exp.timestamp() - datetime.utcnow().timestamp())
    state_value = json.dumps({"jti": refresh_jti, "exp": int(refresh_exp.timestamp())})
    try:
        if ttl > 0:
            await redis_client.setex(f"refresh:{user.id}", ttl, state_value)
    except Exception:
        # Fail-open: authentication still succeeds even if state store fails
        pass

    return {
        "access_token": security.create_access_token(
            subject=user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
        "refresh_token": refresh_token
    }

@router.post("/login/refresh", response_model=Token)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: async_redis.Redis = Depends(get_redis) # Use async get_redis
) -> Any:
    """
    Refresh access token using a refresh token
    """
    # Check Blacklist - use await
    if await redis_client.exists(f"blacklist:{request.refresh_token}"):
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
        presented_jti: str = payload.get("jti")

        if user_id is None or token_type != "refresh" or presented_jti is None:
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

    # Reuse detection: compare against stored JTI
    stored_state_raw = None
    try:
        stored_state_raw = await redis_client.get(f"refresh:{user_id}")
    except Exception:
        stored_state_raw = None  # Fail-open

    if not stored_state_raw:
        # Missing state => either already rotated or logged out
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not recognized or already rotated",
        )

    try:
        stored_state = json.loads(stored_state_raw if isinstance(stored_state_raw, str) else stored_state_raw.decode())
    except Exception:
        stored_state = {}

    if stored_state.get("jti") != presented_jti:
        # Reuse detected (token from older chain) -> Blacklist & force re-login
        try:
            exp = payload.get("exp")
            if exp:
                ttl_old = exp - int(datetime.utcnow().timestamp())
                if ttl_old > 0:
                    await redis_client.setex(f"blacklist:{request.refresh_token}", ttl_old, "true")
        except Exception:
            pass
        # Invalidate current stored chain as precaution
        try:
            if hasattr(redis_client, "delete"):
                await redis_client.delete(f"refresh:{user_id}")
            else:
                await redis_client.setex(f"refresh:{user_id}", 5, json.dumps({"revoked": True}))
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected",
        )
        
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Blacklist the old refresh token (rotate)
    try:
        old_exp = payload.get("exp")
        if old_exp:
            ttl_old = old_exp - int(datetime.utcnow().timestamp())
            if ttl_old > 0:
                await redis_client.setex(f"blacklist:{request.refresh_token}", ttl_old, "true")
    except Exception:
        pass

    # Issue new refresh token with new JTI & persist
    new_jti = str(uuid.uuid4())
    new_refresh_token = security.create_refresh_token(subject=user.id, jti=new_jti)
    new_refresh_exp = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    ttl_new = int(new_refresh_exp.timestamp() - datetime.utcnow().timestamp())
    new_state_value = json.dumps({"jti": new_jti, "exp": int(new_refresh_exp.timestamp())})
    try:
        if ttl_new > 0:
            await redis_client.setex(f"refresh:{user.id}", ttl_new, new_state_value)
    except Exception:
        pass

    return {
        "access_token": security.create_access_token(
            subject=user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
        "refresh_token": new_refresh_token
    }

@router.post("/logout")
async def logout( # Make async
    request: LogoutRequest = None,
    token: str = Depends(oauth2_scheme),
    redis_client: async_redis.Redis = Depends(get_redis) # Use async get_redis
):
    """
    Logout: Blacklist the access token AND refresh token (if provided).
    """
    # 1. Blacklist Access Token - use await
    user_id_for_state = None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        exp = payload.get("exp")
        user_id_for_state = payload.get("sub")
        if exp:
            ttl = exp - int(datetime.utcnow().timestamp())
            if ttl > 0:
                await redis_client.setex(f"blacklist:{token}", ttl, "true")
    except JWTError:
        pass # Already invalid
        
    # 2. Blacklist Refresh Token - use await
    if request and request.refresh_token:
        try:
            payload_r = jwt.decode(request.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            exp_r = payload_r.get("exp")
            if exp_r:
                ttl_r = exp_r - int(datetime.utcnow().timestamp())
                if ttl_r > 0:
                    await redis_client.setex(f"blacklist:{request.refresh_token}", ttl_r, "true")
        except JWTError:
            pass

    # Remove stored refresh state to prevent further rotation
    if user_id_for_state:
        try:
            if hasattr(redis_client, "delete"):
                await redis_client.delete(f"refresh:{user_id_for_state}")
            else:
                # Fallback: short TTL marker
                await redis_client.setex(f"refresh:{user_id_for_state}", 5, json.dumps({"revoked": True}))
        except Exception:
            pass
            
    return {"message": "Successfully logged out"}
