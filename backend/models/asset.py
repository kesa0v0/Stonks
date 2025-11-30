# backend/models/asset.py
import uuid
import enum
from sqlalchemy import Column, String, Boolean, ForeignKey, Enum, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.core.database import Base
from sqlalchemy import event
from backend.models.portfolio_history import PortfolioHistory

class MarketType(enum.Enum):
    KRX = "KRX"
    US = "US"
    CRYPTO = "CRYPTO"
    HUMAN = "HUMAN" # 인간 ETF

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
    symbol = Column(String(50), nullable=False) # 길이를 20 -> 50으로 확장
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


# Portfolio audit hooks
@event.listens_for(Portfolio, "after_insert")
def portfolio_after_insert(mapper, connection, target):
    try:
        reason = getattr(target, "last_update_reason", None)
        connection.execute(
            PortfolioHistory.__table__.insert().values(
                user_id=target.user_id,
                ticker_id=target.ticker_id,
                action="insert",
                prev_quantity=None,
                new_quantity=target.quantity,
                prev_average_price=None,
                new_average_price=target.average_price,
                reason=reason,
            )
        )
    except Exception:
        pass


@event.listens_for(Portfolio, "after_update")
def portfolio_after_update(mapper, connection, target):
    try:
        state = target.__dict__.get("_sa_instance_state").attrs
        qty_hist = state["quantity"].history
        avg_hist = state["average_price"].history
        if qty_hist.has_changes() or avg_hist.has_changes():
            prev_qty = qty_hist.deleted[0] if qty_hist.deleted else None
            prev_avg = avg_hist.deleted[0] if avg_hist.deleted else None
            reason = getattr(target, "last_update_reason", None)
            connection.execute(
                PortfolioHistory.__table__.insert().values(
                    user_id=target.user_id,
                    ticker_id=target.ticker_id,
                    action="update",
                    prev_quantity=prev_qty,
                    new_quantity=target.quantity,
                    prev_average_price=prev_avg,
                    new_average_price=target.average_price,
                    reason=reason,
                )
            )
    except Exception:
        pass


@event.listens_for(Portfolio, "after_delete")
def portfolio_after_delete(mapper, connection, target):
    try:
        reason = getattr(target, "last_update_reason", None)
        connection.execute(
            PortfolioHistory.__table__.insert().values(
                user_id=target.user_id,
                ticker_id=target.ticker_id,
                action="delete",
                prev_quantity=target.quantity,
                new_quantity=None,
                prev_average_price=target.average_price,
                new_average_price=None,
                reason=reason,
            )
        )
    except Exception:
        pass