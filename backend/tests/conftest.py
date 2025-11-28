import sys
import os
from pathlib import Path

# Ensure project root is on sys.path so `import backend` works
ROOT = str(Path(__file__).resolve().parents[2])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock, patch 
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool, NullPool
from sqlalchemy import text
from sqlalchemy import select
from httpx import AsyncClient, ASGITransport
from backend.core.database import Base, get_db
from backend.app.main import app
from backend.core.deps import get_current_user
from backend.models import User, Wallet, Ticker, MarketType, Currency
from backend.core.security import get_password_hash
import uuid
import redis.asyncio as async_redis 
from decimal import Decimal 
from backend.core.cache import get_redis 
import json 

# Helper function to convert Decimals to string for JSON serialization
def convert_decimals_to_str(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: convert_decimals_to_str(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_decimals_to_str(elem) for elem in obj]
    return obj

@pytest_asyncio.fixture(scope="function")
def payload_json_converter():
    return convert_decimals_to_str


# 1. 테스트용 DB URL 결정
# 우선순위:
#  - TEST_DB 토글이 'pg'면 TEST_DATABASE_URL이 있으면 그걸, 없으면 dev 고정 DSN 사용
#  - 그 외에는 TEST_DATABASE_URL, DATABASE_URL, 기본은 SQLite 메모리
TEST_DB_TOGGLE = (os.getenv("TEST_DB") or "").lower().strip()
DEFAULT_DEV_PG_DSN = "postgresql://devuser:devpass@localhost:5432/dev_db"

RAW_DB_URL = None
if TEST_DB_TOGGLE in {"pg", "postgres", "postgresql"}:
    RAW_DB_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or DEFAULT_DEV_PG_DSN
else:
    RAW_DB_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")

is_postgres = False

if RAW_DB_URL:
    url = RAW_DB_URL
    # 컨테이너 내부 호스트명이 'postgres'일 수 있으므로, 호스트에서 테스트 시 localhost로 변경
    # 또한 async 드라이버로 변환
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        is_postgres = True
        url = url.replace("postgres://", "postgresql://")
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # host 교체: postgres -> localhost (도커 포트가 5432로 매핑되어 있어야 함)
        url = url.replace("@postgres:", "@localhost:")
    SQLALCHEMY_DATABASE_URL = url
else:
    SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

if SQLALCHEMY_DATABASE_URL.startswith("sqlite+aiosqlite"):
    engine = create_async_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
else:
    # Postgres 등 외부 DB: 테스트 전용 스키마를 사용하여 격리
    engine = create_async_engine(
        SQLALCHEMY_DATABASE_URL,
        poolclass=NullPool,  # 연결 공유 최소화
        connect_args={
            # asyncpg 전용: 연결 시 search_path 설정
            "server_settings": {"search_path": "test_schema"}
        } if is_postgres else {}
    )

TestingSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

# 2. DB Fixture (Async)
@pytest_asyncio.fixture(scope="function")
async def db_session():
    # 스키마/테이블 생성
    async with engine.begin() as conn:
        if is_postgres:
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS test_schema"))
            # 현재 트랜잭션에서도 적용되도록 search_path 설정 (connect_args에도 있으나 안전망)
            await conn.execute(text("SET search_path TO test_schema"))
        await conn.run_sync(Base.metadata.create_all)
    
    async with TestingSessionLocal() as session:
        yield session
        
    # 정리 (cleanup)
    async with engine.begin() as conn:
        if SQLALCHEMY_DATABASE_URL.startswith("sqlite+aiosqlite"):
            await conn.run_sync(Base.metadata.drop_all)
        elif is_postgres:
            # 스키마 전체를 제거하여 깔끔히 정리
            await conn.execute(text("DROP SCHEMA IF EXISTS test_schema CASCADE"))

@pytest.fixture(scope="function")
def session_factory():
    return TestingSessionLocal

# 4. 테스트 데이터 Fixture (유저, 코인)
@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession): 
    user_id = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6")
    
    hashed = get_password_hash("test1234")
    user = User(
        id=user_id, 
        email="test@test.com", 
        hashed_password=hashed, 
        nickname="Tester",
        is_active=True
    )
    db_session.add(user)
        
    wallet = Wallet(user_id=user_id, balance=Decimal("100000000")) # 1억
    db_session.add(wallet)
    await db_session.commit() 
    
    return user_id

@pytest_asyncio.fixture(scope="function")
async def test_ticker(db_session: AsyncSession): 
    ticker_id = "TEST-COIN"
    ticker = Ticker(
        id=ticker_id, 
        symbol="TEST/KRW", 
        name="Test Coin", 
        market_type=MarketType.CRYPTO,
        currency=Currency.KRW
    )
    db_session.add(ticker)
    await db_session.commit() 
    return ticker_id

# 3. Client Fixture (AsyncClient)
@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession, test_user, mock_external_services): 
    """
    httpx.AsyncClient를 사용하여 비동기 API 테스트
    """
    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        result = await db_session.execute(select(User).where(User.id == test_user))
        return result.scalars().first()
    
    # NEW: Override get_redis to return the mocked instance
    async def override_get_redis():
        return mock_external_services["redis"]

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_redis] = override_get_redis 
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    
    app.dependency_overrides.clear() 

# 5. Redis & RabbitMQ Mocking
@pytest_asyncio.fixture(autouse=True) 
async def mock_external_services(): 
    # REMOVED patch("backend.core.cache.get_redis") 
    # We don't need to patch the function, we just override the dependency.
    
    # Create a generic AsyncMock WITHOUT spec to ensure side_effects work as expected
    mock_redis_instance = AsyncMock() 
    
    # In-memory storage for Redis mock
    redis_data = {}

    # --- Define async side effects for Redis methods ---
    
    async def mock_get(key):
        # Handle both str and bytes keys
        if isinstance(key, bytes):
            key_str = key.decode()
        else:
            key_str = str(key)
        
        # Return stored value if exists
        if key_str in redis_data:
            return redis_data[key_str]

        # Default mock values if not in memory
        if key_str == "config:trading_fee_rate":
            return b"0.001"
        if key_str.startswith("price:"): 
            price_data = {"ticker_id": key_str.split(":")[1], "price": "100.0"}
            return json.dumps(price_data).encode()
        return None 

    # Fix: exists accepts *keys
    async def mock_exists(*keys):
        count = 0
        for key in keys:
            if isinstance(key, bytes):
                key_str = key.decode()
            else:
                key_str = str(key)
            if key_str in redis_data:
                count += 1
        return count

    async def mock_setex(name, time, value):
        if isinstance(name, bytes):
            name_str = name.decode()
        else:
            name_str = str(name)
        redis_data[name_str] = value
        return True
        
    async def mock_set(name, value, ex=None, px=None, nx=False, xx=False, keepttl=False):
        if isinstance(name, bytes):
            name_str = name.decode()
        else:
            name_str = str(name)
        redis_data[name_str] = value
        return True

    async def mock_aclose():
        return None

    # Attach side effects
    mock_redis_instance.get.side_effect = mock_get
    mock_redis_instance.exists.side_effect = mock_exists
    mock_redis_instance.setex.side_effect = mock_setex
    mock_redis_instance.set.side_effect = mock_set
    mock_redis_instance.aclose.side_effect = mock_aclose
    
    # We still need to patch aio_pika as it is not a FastAPI dependency
    with patch("aio_pika.connect_robust") as mock_rabbit: 
        mock_channel = AsyncMock() 
        mock_connection = AsyncMock() 
        mock_connection.channel.return_value = mock_channel
        mock_rabbit.return_value.__aenter__.return_value = mock_connection
        mock_rabbit.return_value.__aexit__.return_value = None 
        
        yield {
            "rabbitmq": mock_rabbit,
            "redis": mock_redis_instance,
            "redis_data": redis_data 
        }