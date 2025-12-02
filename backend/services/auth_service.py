import json
import uuid
from datetime import timedelta, datetime
from typing import Dict, Any, Optional
import redis.asyncio as async_redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import status
from jose import jwt, JWTError, ExpiredSignatureError
from pydantic import ValidationError
from uuid import UUID
import httpx

from backend.core import security, constants
from backend.core.config import settings
from backend.core.exceptions import InvalidCredentialsError, UserInactiveError, UserNotFoundError
from backend.models import User
from backend.schemas.token import RefreshTokenRequest, LogoutRequest

from backend.repository.user import user_repo

async def authenticate_user(
    db: AsyncSession, 
    redis_client: async_redis.Redis, 
    form_data: Any
) -> Dict[str, Any]:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = await user_repo.get_by_email(db, email=form_data.username)
    
    # Check if user exists and has a password (local user)
    if not user or not user.hashed_password or not security.verify_password(form_data.password, user.hashed_password):
        raise InvalidCredentialsError("Incorrect email or password")
    if not user.is_active:
        raise UserInactiveError()
        
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
            await redis_client.setex(f"{constants.REDIS_PREFIX_REFRESH}{user.id}", ttl, state_value)
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

async def authenticate_with_discord(
    db: AsyncSession,
    redis_client: async_redis.Redis,
    code: str,
    redirect_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Exchange Discord OAuth code for user info, upsert user, and issue local tokens.
    """
    # 1) Exchange code → access_token
    token_url = "https://discord.com/api/oauth2/token"
    data = {
        "client_id": settings.DISCORD_CLIENT_ID,
        "client_secret": settings.DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri or settings.DISCORD_REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    async with httpx.AsyncClient(timeout=15) as client:
        token_res = await client.post(token_url, data=data, headers=headers)
        if token_res.status_code >= 300:
            raise InvalidCredentialsError("Discord token exchange failed")
        token_json = token_res.json()
        access_token = token_json.get("access_token")
        if not access_token:
            raise InvalidCredentialsError("Discord did not return access_token")

        # 2) Fetch user info
        user_res = await client.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_res.status_code >= 300:
            raise InvalidCredentialsError("Failed to fetch Discord user info")
        du = user_res.json()

    discord_id = str(du.get("id"))
    username = du.get("global_name") or du.get("username") or "DiscordUser"
    email = du.get("email")
    if not email:
        # Fallback email to satisfy NOT NULL constraint; can be updated later in profile.
        email = f"discord_{discord_id}@placeholder.local"

    # 3) Upsert user by (provider=social_id) or by email
    user = await user_repo.get_by_social(db, provider="discord", social_id=discord_id)
    if not user:
        existing_by_email = await user_repo.get_by_email(db, email=email)
        if existing_by_email:
            # Link Discord to existing account
            existing_by_email.provider = "discord"
            existing_by_email.social_id = discord_id
            if not existing_by_email.nickname:
                existing_by_email.nickname = username[:50]
            db.add(existing_by_email)
            await db.commit()
            await db.refresh(existing_by_email)
            user = existing_by_email
        else:
            # Create new OAuth user (no password)
            user = User(
                email=email,
                hashed_password=None,
                nickname=username[:50],
                is_active=True,
                provider="discord",
                social_id=discord_id,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

    if not user.is_active:
        raise UserInactiveError()

    # 4) Issue tokens (same as local auth)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_jti = str(uuid.uuid4())
    refresh_token = security.create_refresh_token(subject=user.id, jti=refresh_jti)
    refresh_exp = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    ttl = int(refresh_exp.timestamp() - datetime.utcnow().timestamp())
    state_value = json.dumps({"jti": refresh_jti, "exp": int(refresh_exp.timestamp())})
    try:
        if ttl > 0:
            await redis_client.setex(f"{constants.REDIS_PREFIX_REFRESH}{user.id}", ttl, state_value)
    except Exception:
        pass

    return {
        "access_token": security.create_access_token(
            subject=user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
        "refresh_token": refresh_token,
    }

async def refresh_access_token(
    db: AsyncSession, 
    redis_client: async_redis.Redis, 
    request: RefreshTokenRequest
) -> Dict[str, Any]:
    """
    Refresh access token using a refresh token
    """
    # Check Blacklist - use await
    if await redis_client.exists(f"{constants.REDIS_PREFIX_BLACKLIST}{request.refresh_token}"):
        raise InvalidCredentialsError("Refresh token has been revoked")

    try:
        payload = jwt.decode(
            request.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        presented_jti: str = payload.get("jti")

        if user_id is None or token_type != "refresh" or presented_jti is None:
            raise InvalidCredentialsError("Invalid refresh token")
    except ExpiredSignatureError:
        raise InvalidCredentialsError("Refresh token has expired")
    except (JWTError, ValidationError):
        raise InvalidCredentialsError("Invalid refresh token")

    # Reuse detection: compare against stored JTI
    stored_state_raw = None
    try:
        stored_state_raw = await redis_client.get(f"{constants.REDIS_PREFIX_REFRESH}{user_id}")
    except Exception:
        stored_state_raw = None  # Fail-open

    if not stored_state_raw:
        # Missing state => either already rotated or logged out
        raise InvalidCredentialsError("Refresh token not recognized or already rotated")

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
                    await redis_client.setex(f"{constants.REDIS_PREFIX_BLACKLIST}{request.refresh_token}", ttl_old, "true")
        except Exception:
            pass
        # Invalidate current stored chain as precaution
        try:
            if hasattr(redis_client, "delete"):
                await redis_client.delete(f"{constants.REDIS_PREFIX_REFRESH}{user_id}")
            else:
                await redis_client.setex(f"{constants.REDIS_PREFIX_REFRESH}{user_id}", 5, json.dumps({"revoked": True}))
        except Exception:
            pass
        raise InvalidCredentialsError("Refresh token reuse detected")
        
    user = await user_repo.get(db, id=UUID(user_id))
    
    if not user:
        raise UserNotFoundError()
    if not user.is_active:
        raise UserInactiveError()
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Blacklist the old refresh token (rotate)
    try:
        old_exp = payload.get("exp")
        if old_exp:
            ttl_old = old_exp - int(datetime.utcnow().timestamp())
            if ttl_old > 0:
                await redis_client.setex(f"{constants.REDIS_PREFIX_BLACKLIST}{request.refresh_token}", ttl_old, "true")
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
            await redis_client.setex(f"{constants.REDIS_PREFIX_REFRESH}{user.id}", ttl_new, new_state_value)
    except Exception:
        pass

    return {
        "access_token": security.create_access_token(
            subject=user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
        "refresh_token": new_refresh_token
    }

async def logout_user(
    redis_client: async_redis.Redis,
    token: str,
    request: Optional[LogoutRequest] = None
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
                await redis_client.setex(f"{constants.REDIS_PREFIX_BLACKLIST}{token}", ttl, "true")
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
                    await redis_client.setex(f"{constants.REDIS_PREFIX_BLACKLIST}{request.refresh_token}", ttl_r, "true")
        except JWTError:
            pass

    # Remove stored refresh state to prevent further rotation
    if user_id_for_state:
        try:
            if hasattr(redis_client, "delete"):
                await redis_client.delete(f"{constants.REDIS_PREFIX_REFRESH}{user_id_for_state}")
            else:
                # Fallback: short TTL marker
                await redis_client.setex(f"{constants.REDIS_PREFIX_REFRESH}{user_id_for_state}", 5, json.dumps({"revoked": True}))
        except Exception:
            pass
            
    return {"message": "Successfully logged out"}
