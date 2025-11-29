from pydantic import BaseModel, Field
from decimal import Decimal

class IpoCreate(BaseModel):
    quantity: float = Field(..., gt=0, description="발행 주식 수")
    initial_price: float = Field(0, ge=0, description="초기 희망 가격 (평단가로 설정됨)")
    dividend_rate: float = Field(..., ge=0, le=1, description="배당률 (0.0 ~ 1.0)")

class BurnCreate(BaseModel):
    quantity: float = Field(..., gt=0, description="소각할 주식 수")
