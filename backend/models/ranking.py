import uuid
from sqlalchemy import Column, Integer, Numeric, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.core.database import Base

class UserPersona(Base):
    __tablename__ = "user_personas"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)

    # 1. 매매 기본 스탯
    total_trade_count = Column(Integer, default=0, nullable=False) # 매매 중독도
    win_count = Column(Integer, default=0, nullable=False) # 승률
    loss_count = Column(Integer, default=0, nullable=False) 
    
    total_realized_pnl = Column(Numeric(20, 8), default=0, nullable=False) # 누적 실현 손익 (순수익)
    total_profit = Column(Numeric(20, 8), default=0, nullable=False) # 총 익절금
    total_loss = Column(Numeric(20, 8), default=0, nullable=False) # 총 손절금
    total_fees_paid = Column(Numeric(20, 8), default=0, nullable=False) # 수수료 기부왕

    # 2. 성향 지표
    short_position_count = Column(Integer, default=0, nullable=False) # 롱/숏 비율
    long_position_count = Column(Integer, default=0, nullable=False)
    market_order_count = Column(Integer, default=0, nullable=False) # 성격 급한 한국인
    limit_order_count = Column(Integer, default=0, nullable=False)
    
    # 3. 시간대 및 패턴
    night_trade_count = Column(Integer, default=0, nullable=False) # 미국 주식 좀비 (02~05시)
    panic_sell_count = Column(Integer, default=0, nullable=False) # 패닉셀 횟수
    
    # 4. 기록 (High/Low)
    best_trade_pnl = Column(Numeric(20, 8), default=0, nullable=False) # 인생 한방
    worst_trade_pnl = Column(Numeric(20, 8), default=0, nullable=False) # 지옥행 티켓
    
    # 5. 고점매수/저점매도 (인간지표)
    top_buyer_count = Column(Integer, default=0, nullable=False) # 펜트하우스 입주민
    bottom_seller_count = Column(Integer, default=0, nullable=False) # 바닥 청소부

    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User")
