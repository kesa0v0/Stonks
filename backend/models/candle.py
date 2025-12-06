import uuid
from sqlalchemy import Column, String, ForeignKey, Numeric, DateTime, Index, event, DDL
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.core.database import Base

class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        {"postgresql_partition_by": "RANGE (timestamp)"}
    )

    ticker_id = Column(String(50), ForeignKey("tickers.id"), primary_key=True)
    timestamp = Column(DateTime(timezone=True), primary_key=True)
    interval = Column(String(10), primary_key=True, default="1m") # "1m", "1d" 등
    
    open = Column(Numeric(20, 8), nullable=False)
    high = Column(Numeric(20, 8), nullable=False)
    low = Column(Numeric(20, 8), nullable=False)
    close = Column(Numeric(20, 8), nullable=False)
    volume = Column(Numeric(20, 8), nullable=False)

    ticker = relationship("Ticker")

event.listen(
    Candle.__table__,
    "after_create",
    DDL("CREATE TABLE IF NOT EXISTS candles_default PARTITION OF candles DEFAULT")
)
