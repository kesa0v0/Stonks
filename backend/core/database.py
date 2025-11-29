# backend/core/database.py
import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from backend.core.config import settings

# 로거 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# 5. DB 연결 대기 함수 (초기 구동 시 사용)
async def wait_for_db(retries: int = 30, delay: int = 2):
    """데이터베이스가 준비될 때까지 대기합니다."""
    logger.info(f"⏳ Waiting for database... (Max retries: {retries})")
    
    for i in range(retries):
        try:
            # 간단한 쿼리 실행으로 연결 테스트
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("✅ Database is ready!")
            return
        except Exception as e:
            if i == retries - 1:
                logger.error(f"❌ Database connection failed after {retries} attempts: {e}")
                raise e
            
            logger.warning(f"⚠️ Database not ready yet. Retrying in {delay}s... ({i+1}/{retries})")
            await asyncio.sleep(delay)
