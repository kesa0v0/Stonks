from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import secrets
from backend.core.database import get_db
from backend.core.deps import get_current_user
from backend.core import security
from backend.models import ApiKey, User
from backend.schemas.api_key import ApiKeyCreateResponse, ApiKeyItem, ApiKeyListResponse, ApiKeyRotateResponse

router = APIRouter(prefix="/api-keys", tags=["api-keys"])  # RESTful collection

API_KEY_HEADER = "X-API-Key"
KEY_LENGTH = 40  # total plain length
PREFIX_LENGTH = 12  # stored for lookup


def _generate_api_key() -> str:
    # URL-safe random key
    return secrets.token_urlsafe(KEY_LENGTH)

@router.post("/", response_model=ApiKeyCreateResponse)
async def create_api_key(
    name: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    plain_key = _generate_api_key()
    prefix = plain_key[:PREFIX_LENGTH]
    hashed = security.hash_api_key(plain_key)
    api_key = ApiKey(user_id=current_user.id, key_prefix=prefix, hashed_key=hashed, name=name)
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return ApiKeyCreateResponse(key_id=api_key.id, api_key=plain_key, name=name)

@router.get("/", response_model=ApiKeyListResponse)
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(ApiKey).where(ApiKey.user_id == current_user.id))
    items = result.scalars().all()
    return ApiKeyListResponse(items=items)

@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == current_user.id))
    api_key = result.scalars().first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key not found")
    api_key.is_active = False
    await db.commit()
    return None

@router.post("/{key_id}/rotate", response_model=ApiKeyRotateResponse)
async def rotate_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == current_user.id))
    api_key = result.scalars().first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key not found")
    if not api_key.is_active:
        raise HTTPException(status_code=400, detail="API Key is revoked")
    new_plain = _generate_api_key()
    api_key.key_prefix = new_plain[:PREFIX_LENGTH]
    api_key.hashed_key = security.hash_api_key(new_plain)
    await db.commit()
    return ApiKeyRotateResponse(key_id=api_key.id, api_key=new_plain)

# Dependency for API Key authentication
async def get_current_user_by_api_key(
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
    db: AsyncSession = Depends(get_db)
) -> User:
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API Key")
    prefix = x_api_key[:PREFIX_LENGTH]
    result = await db.execute(select(ApiKey).where(ApiKey.key_prefix == prefix, ApiKey.is_active == True))
    candidates = result.scalars().all()
    if not candidates:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")
    for candidate in candidates:
        if security.verify_api_key(x_api_key, candidate.hashed_key):
            # Update last used timestamp
            candidate.last_used_at = candidate.last_used_at or None  # could set to now with server_default
            await db.commit()
            # Fetch user
            user_result = await db.execute(select(User).where(User.id == candidate.user_id))
            user = user_result.scalars().first()
            if not user or not user.is_active:
                raise HTTPException(status_code=401, detail="Inactive user")
            return user
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")
