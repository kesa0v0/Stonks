# backend/schemas/api_key.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID

class ApiKeyCreateResponse(BaseModel):
    key_id: UUID
    api_key: str  # 전체 Key는 최초 발급시에만 반환
    name: Optional[str] = None

class ApiKeyItem(BaseModel):
    key_id: UUID = Field(alias="id")
    name: Optional[str] = None
    key_prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None

    # Pydantic v2: from_attributes replaces orm_mode, populate_by_name keeps alias working both ways
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra='ignore'
    )

class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyItem]

class ApiKeyRotateResponse(BaseModel):
    key_id: UUID
    api_key: str  # 새 Key
