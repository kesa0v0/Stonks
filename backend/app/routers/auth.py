from typing import Any
from fastapi import APIRouter, Depends
from backend.core.rate_limit_config import get_rate_limiter
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as async_redis

from backend.core.database import get_db
from backend.models import User
from backend.schemas.token import Token, RefreshTokenRequest, LogoutRequest, DiscordExchangeRequest
from backend.schemas.user import UserResponse
from backend.core.cache import get_redis
from backend.core.deps import oauth2_scheme, get_current_user
from backend.services.auth_service import authenticate_user, refresh_access_token, logout_user, authenticate_with_discord
from backend.core.config import settings
from urllib.parse import urlencode

router = APIRouter(tags=["authentication"])

@router.get("/login/me", response_model=UserResponse, dependencies=[Depends(get_rate_limiter("/login/me"))])
async def read_current_user_me(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user's information.
    """
    return current_user

@router.post("/login/access-token", response_model=Token, dependencies=[Depends(get_rate_limiter("/login/access-token"))])
async def login_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    redis_client: async_redis.Redis = Depends(get_redis)
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    return await authenticate_user(db, redis_client, form_data)

@router.post("/login/refresh", response_model=Token, dependencies=[Depends(get_rate_limiter("/login/refresh"))])
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: async_redis.Redis = Depends(get_redis) 
) -> Any:
    """
    Refresh access token using a refresh token
    """
    return await refresh_access_token(db, redis_client, request)

@router.post("/logout", dependencies=[Depends(get_rate_limiter("/logout"))])
async def logout(
    request: LogoutRequest = None,
    token: str = Depends(oauth2_scheme),
    redis_client: async_redis.Redis = Depends(get_redis)
):
    """
    Logout: Blacklist the access token AND refresh token (if provided).
    """
    return await logout_user(redis_client, token, request)


# --- Discord OAuth ---
@router.get("/discord/authorize", dependencies=[Depends(get_rate_limiter("/discord/authorize"))])
async def discord_authorize_url():
    """
    Returns the Discord OAuth2 authorization URL. Frontend can redirect to this URL.
    """
    params = {
        "client_id": settings.DISCORD_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.DISCORD_REDIRECT_URI,
        "scope": "identify email guilds",
        "prompt": "consent",
    }
    url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"
    return {"authorization_url": url}

@router.post("/discord/exchange", response_model=Token, dependencies=[Depends(get_rate_limiter("/discord/exchange"))])
async def discord_exchange_code(
    req: DiscordExchangeRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: async_redis.Redis = Depends(get_redis),
):
    """
    Exchange Discord OAuth code to local tokens.
    The `redirect_uri` should match the one used when initiating OAuth.
    """
    return await authenticate_with_discord(db, redis_client, req.code, req.redirect_uri)
