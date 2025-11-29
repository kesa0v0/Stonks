from enum import Enum
from typing import List
from pydantic import BaseModel, ConfigDict
from backend.models.asset import MarketType, Currency

class MarketState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PRE_MARKET = "PRE_MARKET"
    AFTER_MARKET = "AFTER_MARKET"

class MarketStatusResponse(BaseModel):
    krx: MarketState
    us: MarketState
    crypto: MarketState
    server_time: str # ISO format

class TickerResponse(BaseModel):
    id: str
    symbol: str
    name: str
    market_type: MarketType
    currency: Currency
    is_active: bool
    source: str # source 추가 (TickerSource enum이지만 str로 변환되어 나감)

    model_config = ConfigDict(from_attributes=True)

class CurrentPriceResponse(BaseModel):
    ticker_id: str
    price: float | None = None
    message: str | None = None

class OrderBookEntry(BaseModel):
    price: float
    quantity: float

class OrderBookResponse(BaseModel):
    ticker_id: str
    bids: List[OrderBookEntry] # 매수 잔량
    asks: List[OrderBookEntry] # 매도 잔량
