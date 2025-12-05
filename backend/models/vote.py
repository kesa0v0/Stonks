import uuid
import enum
from sqlalchemy import Column, String, ForeignKey, Enum, Boolean, Numeric, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from backend.core.database import Base

class VoteProposalType(enum.Enum):
    DIVIDEND_CHANGE = "DIVIDEND_CHANGE"
    FORCED_DELISTING = "FORCED_DELISTING"
    IMPEACHMENT = "IMPEACHMENT"

class VoteProposalStatus(enum.Enum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

class VoteProposal(Base):
    __tablename__ = "vote_proposals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker_id = Column(String(50), ForeignKey("tickers.id"), nullable=False)
    proposer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    vote_type = Column(Enum(VoteProposalType), nullable=False)
    target_value = Column(String(100), nullable=True)

    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(Enum(VoteProposalStatus), nullable=False, default=VoteProposalStatus.PENDING)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

class Vote(Base):
    __tablename__ = "votes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id = Column(UUID(as_uuid=True), ForeignKey("vote_proposals.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    choice = Column(Boolean, nullable=False)
    quantity = Column(Numeric(20, 8), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
