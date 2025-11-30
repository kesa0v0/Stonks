# backend/models/order.py
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.core.database import Base
from backend.core.enums import OrderType, OrderSide, OrderStatus
from sqlalchemy import event
from backend.models.order_status_history import OrderStatusHistory


class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ticker_id = Column(String(50), ForeignKey("tickers.id"), nullable=False)
    
    side = Column(Enum(OrderSide), nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING, nullable=False)

    # 주문 타입
    type = Column(Enum(OrderType), default=OrderType.MARKET, nullable=False)
    
    # 가격 필드
    target_price = Column(Numeric(20, 8), nullable=True) # LIMIT, STOP_LIMIT(목표가)
    stop_price = Column(Numeric(20, 8), nullable=True)   # STOP_LOSS, TAKE_PROFIT, STOP_LIMIT(발동가)
    
    # Trailing Stop 필드
    trailing_gap = Column(Numeric(20, 8), nullable=True) # 트레일링 간격
    high_water_mark = Column(Numeric(20, 8), nullable=True) # 발동 이후 최고가(매수 시 최저가) 추적용

    # OCO / Linked Orders
    link_id = Column(UUID(as_uuid=True), nullable=True) # 같이 묶인 주문 ID (하나 체결 시 나머지 취소)

    unfilled_quantity = Column(Numeric(20, 8), default=0, nullable=False)
    quantity = Column(Numeric(20, 8), nullable=False)
    price = Column(Numeric(20, 8), nullable=True) # 체결가
    
    realized_pnl = Column(Numeric(20, 8), nullable=True)

    applied_exchange_rate = Column(Numeric(10, 2), default=1.0)
    fee = Column(Numeric(20, 8), default=0)
    fail_reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    filled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="orders")
    ticker = relationship("Ticker")


# Order Status audit hooks
@event.listens_for(Order, "after_insert")
def order_after_insert(mapper, connection, target):
    try:
        reason = getattr(target, "last_update_reason", None) or getattr(target, "fail_reason", None)
        connection.execute(
            OrderStatusHistory.__table__.insert().values(
                order_id=target.id,
                user_id=target.user_id,
                prev_status=None,
                new_status=target.status,
                reason=reason,
            )
        )
    except Exception:
        # don't block main flow on audit issues
        pass


@event.listens_for(Order, "after_update")
def order_after_update(mapper, connection, target):
    try:
        hist = target.__dict__.get("_sa_instance_state").attrs["status"].history
        if hist.has_changes():
            prev_status = hist.deleted[0] if hist.deleted else None
            new_status = target.status
            reason = getattr(target, "last_update_reason", None) or getattr(target, "fail_reason", None)
            connection.execute(
                OrderStatusHistory.__table__.insert().values(
                    order_id=target.id,
                    user_id=target.user_id,
                    prev_status=prev_status,
                    new_status=new_status,
                    reason=reason,
                )
            )
    except Exception:
        pass