# backend/models/user.py
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(200), nullable=True)  # Nullable for OAuth users
    nickname = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    badges = Column(JSON, default=[], nullable=False) # [{"title": "S1 Winner", "date": ...}]

    # OAuth info
    provider = Column(String(20), default="local", nullable=False)  # e.g., "local", "discord"
    social_id = Column(String(100), nullable=True, index=True)  # ID from the provider
    
    # Human ETF & Bankruptcy
    is_bankrupt = Column(Boolean, default=False) # 파산 상태
    bankruptcy_count = Column(Integer, default=0, nullable=False) # 파산 횟수
    dividend_rate = Column(Numeric(5, 4), default=0.5, nullable=False) # 배당률 (기본 50%)

    # Relationships
    wallet = relationship("Wallet", back_populates="user", uselist=False)
    portfolios = relationship("Portfolio", back_populates="user")
    orders = relationship("Order", back_populates="user")

class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    
    # 원화(KRW) 잔고 (소수점 8자리까지 허용하여 정밀도 유지)
    balance = Column(Numeric(20, 8), default=0, nullable=False)
    last_updated = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="wallet")