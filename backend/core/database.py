# backend/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.core.config import settings

# 1. 엔진 생성 (pool_pre_ping=True는 끊긴 연결을 자동 감지해 재연결해줍니다)
engine = create_engine(
    settings.DATABASE_URL, 
    pool_pre_ping=True,
    echo=False  # SQL 로그를 보고 싶으면 True로 변경
)

# 2. 세션 공장 (Session Factory)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 3. 모델들이 상속받을 기본 클래스
Base = declarative_base()

# 4. 의존성 주입용 함수 (FastAPI에서 사용)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()