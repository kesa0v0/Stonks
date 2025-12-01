# backend/schemas/order.py
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from uuid import UUID
from backend.core.enums import OrderType, OrderSide
from backend.schemas.common import DecimalStr


class OrderCreate(BaseModel):
    ticker_id: str = Field()
    side: OrderSide = Field()
    quantity: Decimal = Field(gt=Decimal(0))

    type: OrderType = OrderType.MARKET
    target_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    
    # Trailing Stop 전용
    trailing_gap: Optional[Decimal] = None # 트레일링 간격 (가격 기준)
    
    # OCO (One Cancels Other) 링크용 - 클라이언트에서 보낼 땐 보통 두 개의 주문을 한번에 보내지만,
    # 여기선 간단히 "이 주문을 만들 때 다른 주문 ID와 연결"하는 방식보다는,
    # 서비스 단에서 두 주문을 생성하고 묶는게 나음.
    # 일단 단일 주문 생성 필드로는 이정도가 적당함.

class OrderResponse(BaseModel):
    order_id: str
    status: str
    message: str
    ticker_id: Optional[str] = None
    side: Optional[str] = None
    type: Optional[str] = None
    quantity: Optional[DecimalStr] = None
    target_price: Optional[DecimalStr] = None
    stop_price: Optional[DecimalStr] = None
    trailing_gap: Optional[DecimalStr] = None
    price: Optional[DecimalStr] = None
    unfilled_quantity: Optional[DecimalStr] = None
    created_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    fail_reason: Optional[str] = None
    user_id: Optional[str] = None
    link_id: Optional[str] = None # OCO Group ID

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra='ignore'
    )

class OrderListResponse(BaseModel):
    id: UUID
    ticker_id: str
    side: str
    status: str
    quantity: DecimalStr
    price: Optional[DecimalStr] = None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra='ignore'
    )