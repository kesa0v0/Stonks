from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from backend.models.asset import MarketType, Currency, TickerSource
from backend.schemas.common import DecimalStr

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

class TickerCreate(BaseModel):
    id: str # 관리자가 직접 입력
    symbol: str
    name: str
    market_type: MarketType
    currency: Currency
    source: TickerSource = TickerSource.UPBIT
    is_active: bool = True

class TickerUpdate(BaseModel):
    symbol: Optional[str] = None
    name: Optional[str] = None
    market_type: Optional[MarketType] = None
    currency: Optional[Currency] = None
    source: Optional[TickerSource] = None
    is_active: Optional[bool] = None

class TickerResponse(BaseModel):
    id: str
    symbol: str
    name: str
    market_type: MarketType
    currency: Currency
    is_active: bool
    source: str # source 추가 (TickerSource enum이지만 str로 변환되어 나감)
    
    # Market Data (Optional)
    current_price: Optional[DecimalStr] = None
    change_percent: Optional[DecimalStr] = None
    volume: Optional[DecimalStr] = None

    model_config = ConfigDict(from_attributes=True)

class CurrentPriceResponse(BaseModel):
    ticker_id: str
    price: DecimalStr | None = None
    message: str | None = None

class OrderBookEntry(BaseModel):
    price: DecimalStr
    quantity: DecimalStr

class OrderBookResponse(BaseModel):
    ticker_id: str
    bids: List[OrderBookEntry] # 매수 잔량
    asks: List[OrderBookEntry] # 매도 잔량

class MoverResponse(BaseModel):
    ticker: TickerResponse
    price: DecimalStr
    change_percent: DecimalStr
    volume: DecimalStr # 해당 기간(1m 등)의 거래량
    value: DecimalStr # 거래대금 (price * volume)
