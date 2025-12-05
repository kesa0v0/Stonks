from typing import Optional, Dict
from pydantic import BaseModel
from backend.schemas.common import DecimalStr

class RankingEntry(BaseModel):
    rank: int
    nickname: str
    value: DecimalStr
    extra_info: Optional[dict] = None

class HallOfFameResponse(BaseModel):
    top_profit: Optional[RankingEntry] = None
    top_loss: Optional[RankingEntry] = None
    top_volume: Optional[RankingEntry] = None
    top_win_rate: Optional[RankingEntry] = None
    top_fees: Optional[RankingEntry] = None
    top_night: Optional[RankingEntry] = None
    top_dividend: Optional[RankingEntry] = None
