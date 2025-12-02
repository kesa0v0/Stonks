from pydantic import BaseModel
from backend.schemas.market import TickerResponse

class WatchlistItemResponse(BaseModel):
    ticker: TickerResponse
    current_price: float
