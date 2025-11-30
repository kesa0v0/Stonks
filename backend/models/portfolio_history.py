import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from backend.core.database import Base


class PortfolioHistory(Base):
    __tablename__ = "portfolio_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ticker_id = Column(String(50), ForeignKey("tickers.id"), nullable=False)

    action = Column(String(20), nullable=False)  # insert | update | delete

    prev_quantity = Column(Numeric(20, 8), nullable=True)
    new_quantity = Column(Numeric(20, 8), nullable=True)
    prev_average_price = Column(Numeric(20, 8), nullable=True)
    new_average_price = Column(Numeric(20, 8), nullable=True)

    reason = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
