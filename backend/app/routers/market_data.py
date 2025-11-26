from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from decimal import Decimal

from backend.services.trade_service import get_current_price

router = APIRouter(prefix="/market-data", tags=["market-data"])

class CurrentPriceResponse(BaseModel):
    ticker_id: str
    price: Optional[float] = None
    message: Optional[str] = None

@router.get("/price/{ticker_id}", response_model=CurrentPriceResponse)
def get_ticker_current_price(ticker_id: str):
    """
    특정 티커의 현재 시장 가격을 조회합니다.
    """
    price_decimal = get_current_price(ticker_id)
    
    if price_decimal is None:
        return CurrentPriceResponse(
            ticker_id=ticker_id,
            price=None,
            message=f"Price data not available for {ticker_id}"
        )
    
    return CurrentPriceResponse(
        ticker_id=ticker_id,
        price=float(price_decimal)
    )