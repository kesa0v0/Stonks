from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from backend.core.database import Base

class Season(Base):
    __tablename__ = "seasons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False) # e.g. "Season 1", "2024-Nov League"
    start_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    description = Column(String, nullable=True)
