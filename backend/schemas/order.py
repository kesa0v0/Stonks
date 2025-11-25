# backend/schemas/order.py
from pydantic import BaseModel, Field
from enum import Enum
from decimal import Decimal
from typing import Optional

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