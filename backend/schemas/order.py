# backend/schemas/order.py
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum
from decimal import Decimal
from uuid import UUID

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderCreate(BaseModel):
    ticker_id: str = Field()
    side: OrderSide = Field()
    quantity: Decimal = Field(gt=0)

class OrderResponse(BaseModel):
    order_id: str
    status: str
    message: str

# 거래 내역 조회용 스키마
class OrderListResponse(BaseModel):
    id: UUID
    ticker_id: str
    side: str
    status: str
    quantity: float
    price: float
    created_at: datetime # 주문 시간

    class Config:
        from_attributes = True # ORM 객체를 Pydantic으로 자동 변환