from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from backend.core.database import get_db
from backend.core.deps import get_current_user
from backend.models import User
from backend.schemas.api_key import ApiKeyCreateResponse, ApiKeyListResponse, ApiKeyRotateResponse, ApiKeyCreateRequest
from backend.services.api_key_service import create_new_api_key, get_user_api_keys, revoke_user_api_key, rotate_user_api_key

router = APIRouter(prefix="/api-keys", tags=["api-keys"])  # RESTful collection

@router.post("/", response_model=ApiKeyCreateResponse)
async def create_api_key(
    request: ApiKeyCreateRequest = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await create_new_api_key(db, current_user.id, request)

@router.get("/", response_model=ApiKeyListResponse)
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    items = await get_user_api_keys(db, current_user.id)
    return ApiKeyListResponse(items=items)

@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    await revoke_user_api_key(db, current_user.id, key_id)

@router.post("/{key_id}/rotate", response_model=ApiKeyRotateResponse)
async def rotate_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await rotate_user_api_key(db, current_user.id, key_id)
