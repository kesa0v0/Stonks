from datetime import datetime
from pydantic import BaseModel, ConfigDict
from decimal import Decimal

class CandleResponse(BaseModel):
    ticker_id: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    model_config = ConfigDict(from_attributes=True)
