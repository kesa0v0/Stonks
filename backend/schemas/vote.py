from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, validator, field_serializer
from pydantic.config import ConfigDict
from uuid import UUID

from backend.schemas.common import DecimalStr
from backend.models.vote import VoteProposalType, VoteProposalStatus
from backend.core import constants # New import


def _ensure_tz(dt: Optional[datetime]) -> datetime:
    """Coerce datetime (or string) to timezone-aware UTC."""
    if dt is None:
        return datetime.now(timezone.utc)
    if isinstance(dt, str):
        # Handle common ISO strings, including trailing 'Z'
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)
    if dt is None:
        return datetime.now(timezone.utc)
    # At this point dt is datetime
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class VoteProposalCreate(BaseModel):
    ticker_id: str = Field(..., description="Target ticker for the proposal")
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    vote_type: VoteProposalType
    target_value: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: datetime

    @validator("start_at")
    def normalize_start(cls, v):
        if v is None:
            return v
        return _ensure_tz(v)

    @validator("end_at")
    def validate_window(cls, v, values):
        start = values.get("start_at") or datetime.now(timezone.utc)
        # Normalize both datetimes to be timezone-aware before comparing
        start = _ensure_tz(start)
        v = _ensure_tz(v)
        if v <= start:
            raise ValueError("end_at must be after start_at")
        return v

    @validator("target_value", pre=True, always=True)
    def validate_target_value_by_type(cls, v, values):
        vote_type = values.get("vote_type")
        if vote_type == VoteProposalType.DIVIDEND_CHANGE:
            if v is None:
                raise ValueError("target_value is required for DIVIDEND_CHANGE proposals")
            try:
                rate = Decimal(v)
                min_rate = Decimal(str(constants.HUMAN_DIVIDEND_RATE_NORMAL_MIN))
                max_rate = Decimal(str(constants.HUMAN_DIVIDEND_RATE_MAX))
                if not (min_rate <= rate <= max_rate):
                    raise ValueError(f"Dividend rate must be between {min_rate*100}% and {max_rate*100}%")
            except Exception:
                raise ValueError("target_value for DIVIDEND_CHANGE must be a valid decimal string")
        elif vote_type in [VoteProposalType.FORCED_DELISTING, VoteProposalType.IMPEACHMENT]:
            if v is not None:
                raise ValueError(f"target_value should not be set for {vote_type.value} proposals")
        return v

class VoteProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
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

    @field_serializer("id")
    def serialize_id(self, v: UUID):
        return str(v)

class VoteCastRequest(BaseModel):
    choice: bool = Field(..., description="True=Yes, False=No")
    quantity: Decimal = Field(..., gt=0)

class VoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    proposal_id: UUID
    user_id: UUID
    choice: bool
    quantity: DecimalStr
    created_at: Optional[datetime] = None

    @field_serializer("proposal_id")
    def serialize_proposal_id(self, v: UUID):
        return str(v)

    @field_serializer("user_id")
    def serialize_user_id(self, v: UUID):
        return str(v)

class ProposalTally(BaseModel):
    yes: DecimalStr
    no: DecimalStr

class ProposalDetail(VoteProposalOut):
    tally: ProposalTally
    my_vote: Optional[VoteOut] = None

class ProposalList(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    items: List[VoteProposalOut]
