from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, validator

from backend.schemas.common import DecimalStr
from backend.models.vote import VoteProposalType, VoteProposalStatus


class VoteProposalCreate(BaseModel):
    ticker_id: str = Field(..., description="Target ticker for the proposal")
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    vote_type: VoteProposalType
    target_value: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: datetime

    @validator("end_at")
    def validate_window(cls, v, values):
        start = values.get("start_at") or datetime.utcnow()
        if v <= start:
            raise ValueError("end_at must be after start_at")
        return v

class VoteProposalOut(BaseModel):
    id: str
    ticker_id: str
    title: str
    description: Optional[str]
    vote_type: VoteProposalType
    target_value: Optional[str]
    start_at: datetime
    end_at: datetime
    status: VoteProposalStatus
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True

class VoteCastRequest(BaseModel):
    choice: bool = Field(..., description="True=Yes, False=No")
    quantity: Decimal = Field(..., gt=0)

class VoteOut(BaseModel):
    proposal_id: str
    user_id: str
    choice: bool
    quantity: DecimalStr
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True

class ProposalTally(BaseModel):
    yes: DecimalStr
    no: DecimalStr

class ProposalDetail(VoteProposalOut):
    tally: ProposalTally
    my_vote: Optional[VoteOut] = None

class ProposalList(BaseModel):
    items: List[VoteProposalOut]
