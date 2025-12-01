from pydantic import BaseModel, Field
from decimal import Decimal

class FeeUpdate(BaseModel):
    fee_rate: Decimal = Field(..., ge=0.0, le=1.0, description="Trading fee rate (e.g., 0.001 for 0.1%)")

class PriceUpdate(BaseModel):
    ticker_id: str
    price: Decimal
