from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID

class GuestbookCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=500, description="방명록 내용")

class GuestbookResponse(BaseModel):
    id: UUID
    ticker_id: str
    user_id: UUID
    nickname: str
    content: str
    created_at: datetime
    is_issuer: bool # 작성자가 발행자인지 여부
