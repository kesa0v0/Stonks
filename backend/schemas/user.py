from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, EmailStr
from uuid import UUID
from backend.schemas.common import DecimalStr

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
    badges: List[Dict[str, Any]]
    is_bankrupt: Optional[bool] = False
    dividend_rate: Optional[DecimalStr] = "0.5"
    
    model_config = ConfigDict(from_attributes=True)

class UserProfileResponse(BaseModel):
    id: UUID
    nickname: str
    badges: List[Dict[str, Any]]
    profit_rate: Optional[DecimalStr] = None # 공개 여부에 따라 달라짐
    
    model_config = ConfigDict(from_attributes=True)
