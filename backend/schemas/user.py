from typing import Optional
from pydantic import BaseModel, ConfigDict
from uuid import UUID

class UserResponse(BaseModel):
    id: UUID
    email: str
    nickname: str
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)
