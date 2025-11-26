# backend/models/order.py
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.core.database import Base
from backend.core.enums import OrderType, OrderSide, OrderStatus


class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ticker_id = Column(String(50), ForeignKey("tickers.id"), nullable=False)
    
    side = Column(Enum(OrderSide), nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING, nullable=False)

    # 주문 타입 (기본값은 시장가)
    type = Column(Enum(OrderType), default=OrderType.MARKET, nullable=False)
    # 지정가 가격 (시장가면 null)
    target_price = Column(Numeric(20, 8), nullable=True)

    # 미체결 잔량 (부분 체결 대비, 일단은 quantity와 똑같이 시작)
    unfilled_quantity = Column(Numeric(20, 8), default=0, nullable=False)
    quantity = Column(Numeric(20, 8), nullable=False)
    price = Column(Numeric(20, 8), nullable=True) # 체결가
    
    applied_exchange_rate = Column(Numeric(10, 2), default=1.0)
    fee = Column(Numeric(20, 8), default=0)
    fail_reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    filled_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="orders")
    ticker = relationship("Ticker")