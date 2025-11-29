from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr
from uuid import UUID

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    nickname: str

class UserUpdate(BaseModel):
    password: Optional[str] = None
    nickname: Optional[str] = None
    is_active: Optional[bool] = None

class UserResponse(BaseModel):
    id: UUID
    email: str
    nickname: str
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)
