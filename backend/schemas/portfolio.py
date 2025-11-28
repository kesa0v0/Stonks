# backend/schemas/portfolio.py
from pydantic import BaseModel, ConfigDict
from typing import List
from decimal import Decimal

class AssetResponse(BaseModel):
    ticker_id: str
    symbol: str
    name: str
    quantity: float
    average_price: float
    current_price: float  # 현재가 (Redis에서 가져옴)
    total_value: float    # 평가 금액 (수량 * 현재가)
    profit_rate: float    # 수익률 (%)

class PortfolioResponse(BaseModel):
    cash_balance: float
    total_asset_value: float # 총 자산 (현금 + 주식 평가액)
    assets: List[AssetResponse]
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra='ignore'
    )

AssetResponse.model_config = ConfigDict(
    from_attributes=True,
    populate_by_name=True,
    extra='ignore'
)