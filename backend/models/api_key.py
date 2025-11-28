# backend/models/api_key.py
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.core.database import Base

class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    key_prefix = Column(String(16), nullable=False, index=True)  # 첫 몇 글자 (평문 일부)로 탐색 최적화
    hashed_key = Column(String(256), nullable=False)  # 전체 API Key 해시(Argon2)
    name = Column(String(100), nullable=True)  # 사용자 지정 이름
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True, index=True)

    user = relationship("User", backref="api_keys")
