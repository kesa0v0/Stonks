from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import secrets

from backend.core import security, constants
from backend.core.exceptions import ApiKeyNotFoundError, ApiKeyRevokedError
from backend.models import ApiKey, User
from backend.schemas.api_key import ApiKeyCreateResponse, ApiKeyRotateResponse, ApiKeyCreateRequest

def _generate_api_key() -> str:
    # URL-safe random key
    return secrets.token_urlsafe(constants.API_KEY_LENGTH)

async def create_new_api_key(
    db: AsyncSession, 
    user_id: UUID, 
    request: ApiKeyCreateRequest = None
) -> ApiKeyCreateResponse:
    name = request.name if request else None
    plain_key = _generate_api_key()
    prefix = plain_key[:constants.API_KEY_PREFIX_LENGTH]
    hashed = security.hash_api_key(plain_key)
    api_key = ApiKey(user_id=user_id, key_prefix=prefix, hashed_key=hashed, name=name)
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return ApiKeyCreateResponse(key_id=api_key.id, api_key=plain_key, name=name)

async def get_user_api_keys(db: AsyncSession, user_id: UUID):
    result = await db.execute(select(ApiKey).where(ApiKey.user_id == user_id))
    items = result.scalars().all()
    return items

async def revoke_user_api_key(db: AsyncSession, user_id: UUID, key_id: UUID):
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id))
    api_key = result.scalars().first()
    if not api_key:
        raise ApiKeyNotFoundError()
    api_key.is_active = False
    await db.commit()

async def rotate_user_api_key(db: AsyncSession, user_id: UUID, key_id: UUID) -> ApiKeyRotateResponse:
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id))
    api_key = result.scalars().first()
    if not api_key:
        raise ApiKeyNotFoundError()
    if not api_key.is_active:
        raise ApiKeyRevokedError("API Key is revoked")
    new_plain = _generate_api_key()
    api_key.key_prefix = new_plain[:constants.API_KEY_PREFIX_LENGTH]
    api_key.hashed_key = security.hash_api_key(new_plain)
    await db.commit()
    return ApiKeyRotateResponse(key_id=api_key.id, api_key=new_plain)
