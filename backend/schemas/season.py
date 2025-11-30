from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SeasonBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool

class SeasonCreate(SeasonBase):
    pass

class SeasonResponse(SeasonBase):
    id: int
    start_date: datetime
    end_date: Optional[datetime]

    class Config:
        from_attributes = True
