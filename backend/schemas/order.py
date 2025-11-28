# backend/schemas/order.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict # Pydantic V2 ConfigDict import
from decimal import Decimal
from uuid import UUID
from backend.core.enums import OrderType, OrderSide


class OrderCreate(BaseModel):
    ticker_id: str = Field()
    side: OrderSide = Field()
    quantity: Decimal = Field(gt=Decimal(0)) # Change to Decimal

    type: OrderType = OrderType.MARKET # 안 보내면 시장가
    target_price: Optional[Decimal] = None # 지정가일 때만 필수 # Change to Decimal

class OrderResponse(BaseModel):
    order_id: str
    status: str
    message: str
    ticker_id: Optional[str] = None
    side: Optional[str] = None
    type: Optional[str] = None
    quantity: Optional[float] = None
    target_price: Optional[float] = None
    price: Optional[float] = None
    unfilled_quantity: Optional[float] = None
    created_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    fail_reason: Optional[str] = None
    user_id: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra='ignore'
    )

# 거래 내역 조회용 스키마
class OrderListResponse(BaseModel):
    id: UUID
    ticker_id: str
    side: str
    status: str
    quantity: float # This can remain float for display
    price: Optional[float] = None # 미체결 시 None일 수 있음 # This can remain float for display
    created_at: datetime # 주문 시간

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra='ignore'
    )