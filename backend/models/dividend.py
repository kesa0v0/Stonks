import uuid
from sqlalchemy import Column, Numeric, ForeignKey, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from backend.core.database import Base

class DividendHistory(Base):
    __tablename__ = "dividend_histories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    payer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False) # 배당을 지급한 사람 (노예/발행자)
    receiver_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False) # 배당을 받은 사람 (주주)
    
    ticker_id = Column(String(50), nullable=False) # 어떤 주식 때문에 배당받았는지 (HUMAN_XXX)
    amount = Column(Numeric(20, 8), nullable=False) # 배당 금액
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
