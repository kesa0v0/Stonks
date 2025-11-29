from enum import Enum
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

    model_config = ConfigDict(from_attributes=True)

class CurrentPriceResponse(BaseModel):
    ticker_id: str
    price: float | None = None
    message: str | None = None
