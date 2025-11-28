from pydantic import BaseModel, ConfigDict
from backend.models.asset import MarketType, Currency

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
