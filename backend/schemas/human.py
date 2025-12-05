from pydantic import BaseModel, Field
from decimal import Decimal
from typing import List
from backend.schemas.common import DecimalStr
from datetime import datetime

class IpoCreate(BaseModel):
    quantity: Decimal = Field(..., gt=0, description="발행 주식 수")
    initial_price: Decimal = Field(0, ge=0, description="초기 희망 가격 (평단가로 설정됨)")
    dividend_rate: Decimal = Field(..., ge=0, le=1, description="배당률 (0.0 ~ 1.0)")

class BurnCreate(BaseModel):
    quantity: Decimal = Field(..., gt=0, description="소각할 주식 수")

class Shareholder(BaseModel):
    rank: int
    nickname: str
    quantity: DecimalStr
    percentage: float # 지분율 (%)

class ShareholderResponse(BaseModel):
    total_issued: DecimalStr # 총 발행량 (나 포함)
    my_holdings: DecimalStr # 내가 보유한 양
    shareholders: List[Shareholder]

class DividendPaymentEntry(BaseModel):
    date: datetime
    source_pnl: DecimalStr # 원천 수익 (배당 계산의 기준이 된 PnL)
    paid_amount: DecimalStr # 실제로 지급된 배당금
    ticker_id: str

class IssuerDividendStats(BaseModel):
    current_dividend_rate: DecimalStr # 현재 설정된 배당률 (예: 0.50)
    cumulative_paid_amount: DecimalStr # 누적 배당 지급액

class UpdateDividendRate(BaseModel):
    dividend_rate: Decimal = Field(..., ge=0, le=1, description="배당률 (0.0 ~ 1.0)")
