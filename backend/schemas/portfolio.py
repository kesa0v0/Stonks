# backend/schemas/portfolio.py
from pydantic import BaseModel, ConfigDict
from typing import List
from decimal import Decimal
from datetime import date
from backend.schemas.common import DecimalStr

class AssetResponse(BaseModel):
    ticker_id: str
    symbol: str
    name: str
    quantity: DecimalStr
    average_price: DecimalStr
    current_price: DecimalStr  # 현재가 (Redis에서 가져옴)
    total_value: DecimalStr    # 평가 금액 (수량 * 현재가)
    profit_rate: DecimalStr    # 수익률 (%)

class PortfolioResponse(BaseModel):
    cash_balance: DecimalStr
    total_asset_value: DecimalStr # 총 자산 (현금 + 주식 평가액)
    assets: List[AssetResponse]
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra='ignore'
    )

class PnLResponse(BaseModel):
    start_date: date
    end_date: date
    realized_pnl: DecimalStr
    
AssetResponse.model_config = ConfigDict(
    from_attributes=True,
    populate_by_name=True,
    extra='ignore'
)