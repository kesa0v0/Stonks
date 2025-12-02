from pydantic import BaseModel, Field, conint
from decimal import Decimal

class FeeUpdate(BaseModel):
    fee_rate: Decimal = Field(..., ge=0.0, le=1.0, description="Trading fee rate (e.g., 0.001 for 0.1%)")

class PriceUpdate(BaseModel):
    ticker_id: str
    price: Decimal

class WhaleThresholdUpdate(BaseModel):
    whale_threshold_krw: conint(ge=0) = Field(..., description="Whale alert threshold in KRW")

class MessageTemplateUpdate(BaseModel):
    key: str = Field(..., description="Template key (e.g., whale_trade)")
    content: str = Field(..., description="Template content with placeholders")

class MessageTemplateResponse(BaseModel):
    key: str
    content: str
