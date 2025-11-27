# backend/core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from backend.core.config import settings

# 1. 비동기 엔진 생성
# echo=True로 설정하면 실행되는 SQL이 로그에 찍힙니다. (디버깅용)
engine = create_async_engine(
    settings.ASYNC_DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True # 연결 끊김 자동 감지
)

# 2. 비동기 세션 공장 (Async Session Factory)
# expire_on_commit=False: 커밋 후에도 객체 속성에 접근할 수 있도록 설정 (비동기에서 중요)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

# 3. 모델들이 상속받을 기본 클래스
Base = declarative_base()

# 4. 의존성 주입용 함수 (FastAPI에서 사용)
# async generator를 사용해야 합니다.
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
