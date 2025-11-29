from typing import Any
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as async_redis

from backend.core.database import get_db
from backend.models import User
from backend.schemas.token import Token, RefreshTokenRequest, LogoutRequest
from backend.schemas.user import UserResponse
from backend.core.cache import get_redis
from backend.core.deps import oauth2_scheme, get_current_user
from backend.services.auth_service import authenticate_user, refresh_access_token, logout_user

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
    return await authenticate_user(db, redis_client, form_data)

@router.post("/login/refresh", response_model=Token)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: async_redis.Redis = Depends(get_redis) 
) -> Any:
    """
    Refresh access token using a refresh token
    """
    return await refresh_access_token(db, redis_client, request)

@router.post("/logout")
async def logout(
    request: LogoutRequest = None,
    token: str = Depends(oauth2_scheme),
    redis_client: async_redis.Redis = Depends(get_redis)
):
    """
    Logout: Blacklist the access token AND refresh token (if provided).
    """
    return await logout_user(redis_client, token, request)
