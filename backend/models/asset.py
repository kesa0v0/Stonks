# backend/models/asset.py
import uuid
import enum
from sqlalchemy import Column, String, Boolean, ForeignKey, Enum, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.core.database import Base

class MarketType(enum.Enum):
    KRX = "KRX"
    US = "US"
    CRYPTO = "CRYPTO"

class Currency(enum.Enum):
    KRW = "KRW"
    USD = "USD"

class TickerSource(enum.Enum):
    UPBIT = "UPBIT"
    MOCK = "MOCK"
    TEST = "TEST"

class Ticker(Base):
    __tablename__ = "tickers"

    id = Column(String(50), primary_key=True)  # 예: KRX-STOCK-005930
    symbol = Column(String(20), nullable=False)
    name = Column(String(100), nullable=False)
    market_type = Column(Enum(MarketType), nullable=False)
    currency = Column(Enum(Currency), nullable=False)
    # 소스 추가 (기본값 UPBIT)
    source = Column(Enum(TickerSource), default=TickerSource.UPBIT, nullable=False)
    is_active = Column(Boolean, default=True)

class Portfolio(Base):
    __tablename__ = "portfolios"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ticker_id = Column(String(50), ForeignKey("tickers.id"), nullable=False)
    
    quantity = Column(Numeric(20, 8), default=0, nullable=False)
    average_price = Column(Numeric(20, 8), default=0, nullable=False)
    
    user = relationship("User", back_populates="portfolios")
    ticker = relationship("Ticker")