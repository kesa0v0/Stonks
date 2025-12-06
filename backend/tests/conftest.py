import sys
import os
from pathlib import Path

# Ensure project root is on sys.path so `import backend` works
ROOT = str(Path(__file__).resolve().parents[2])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


from fastapi_limiter import FastAPILimiter
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
from backend.core.security import get_password_hash, create_access_token
from fastapi import Request
from jose import jwt, JWTError
from backend.core.config import settings
import uuid
import redis.asyncio as async_redis 
from decimal import Decimal 
from backend.core.cache import get_redis 
import json 


# 6. FastAPILimiter 초기화 (테스트 환경)
@pytest_asyncio.fixture(autouse=True)
async def fastapi_limiter_init(mock_external_services):
    # Redis mock 인스턴스 사용
    await FastAPILimiter.init(mock_external_services["redis"])

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

TEST_DB_TOGGLE = "pg" # pg or sqlite
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

# Additional user/token fixture for forbidden access tests
@pytest_asyncio.fixture(scope="function")
async def another_user_token(db_session: AsyncSession):
    other_id = uuid.uuid4()
    hashed = get_password_hash("otherpass123")
    other = User(
        id=other_id,
        email="other@test.com",
        hashed_password=hashed,
        nickname="Other",
        is_active=True
    )
    db_session.add(other)
    db_session.add(Wallet(user_id=other_id, balance=Decimal("500000")))
    await db_session.commit()
    token = create_access_token(subject=other_id)
    return token

@pytest_asyncio.fixture(scope="function")
async def admin_user(db_session: AsyncSession):
    """
    Creates an admin user for testing.
    """
    admin_id = uuid.uuid4()
    hashed = get_password_hash("admin1234")
    admin = User(
        id=admin_id,
        email=settings.ADMIN_EMAIL, # Use the configured ADMIN_EMAIL
        hashed_password=hashed,
        nickname="AdminUser",
        is_active=True
    )
    db_session.add(admin)
    db_session.add(Wallet(user_id=admin_id, balance=Decimal("1000000000"))) # Large balance for admin
    await db_session.commit()
    return admin

@pytest_asyncio.fixture(scope="function")
async def admin_user_token(admin_user: User):
    """
    Generates an access token for the admin user.
    """
    token = create_access_token(subject=admin_user.id)
    return token

# 3. Client Fixture (AsyncClient)
@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession, test_user, mock_external_services): 
    """
    httpx.AsyncClient를 사용하여 비동기 API 테스트
    """
    async def override_get_db():
        yield db_session

    async def override_get_current_user(request: Request):
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]
            try:
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                sub = payload.get("sub")
                ttype = payload.get("type")
                if sub and ttype == "access":
                    result2 = await db_session.execute(select(User).where(User.id == uuid.UUID(sub)))
                    user2 = result2.scalars().first()
                    if user2:
                        return user2
            except (JWTError, ValueError):
                from fastapi import HTTPException
                raise HTTPException(status_code=401, detail="Could not validate credentials")
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
    
    # New Redis Methods for Order Cache
    async def mock_zadd(name, mapping, **kwargs):
        name_str = str(name)
        if name_str not in redis_data:
            redis_data[name_str] = [] # List of (score, member)
        
        # Mapping is {member: score}
        for member, score in mapping.items():
            # Remove existing if any
            redis_data[name_str] = [x for x in redis_data[name_str] if x[1] != str(member)]
            redis_data[name_str].append((float(score), str(member)))
        
        # Sort by score
        redis_data[name_str].sort(key=lambda x: x[0])
        return len(mapping)

    async def mock_zrangebyscore(name, min_score, max_score, **kwargs):
        name_str = str(name)
        if name_str not in redis_data:
            return []
        
        res = []
        for score, member in redis_data[name_str]:
            # Handle inf
            if min_score != "-inf" and score < float(min_score):
                continue
            if max_score != "+inf" and score > float(max_score):
                continue
            res.append(member)
        return res

    async def mock_zrem(name, *values):
        name_str = str(name)
        if name_str not in redis_data:
            return 0
        
        original_len = len(redis_data[name_str])
        redis_data[name_str] = [x for x in redis_data[name_str] if x[1] not in [str(v) for v in values]]
        return original_len - len(redis_data[name_str])

    async def mock_hset(name, mapping):
        name_str = str(name)
        if name_str not in redis_data:
            redis_data[name_str] = {}
        
        # Allow simple dict simulation for Hash
        if not isinstance(redis_data[name_str], dict):
             redis_data[name_str] = {}

        for k, v in mapping.items():
            redis_data[name_str][str(k)] = str(v)
        return len(mapping)

    async def mock_hgetall(name):
        name_str = str(name)
        return redis_data.get(name_str, {})

    async def mock_delete(*names):
        count = 0
        for name in names:
            name_str = str(name)
            if name_str in redis_data:
                del redis_data[name_str]
                count += 1
        return count

    mock_redis_instance.zadd.side_effect = mock_zadd
    mock_redis_instance.zrangebyscore.side_effect = mock_zrangebyscore
    mock_redis_instance.zrem.side_effect = mock_zrem
    mock_redis_instance.hset.side_effect = mock_hset
    mock_redis_instance.hgetall.side_effect = mock_hgetall
    mock_redis_instance.delete.side_effect = mock_delete

    # Mock Pipeline
    class MockPipeline:
        def __init__(self):
            self.commands = []
            
        def zadd(self, name, mapping):
            self.commands.append((mock_zadd, (name, mapping)))
            return self
            
        def zrem(self, name, *values):
            self.commands.append((mock_zrem, (name, *values)))
            return self
            
        def hset(self, name, mapping):
            self.commands.append((mock_hset, (name, mapping)))
            return self
            
        def delete(self, *names):
            self.commands.append((mock_delete, names))
            return self

        async def execute(self):
            results = []
            for func, args in self.commands:
                results.append(await func(*args))
            return results

    # pipeline() should be synchronous and return MockPipeline
    mock_redis_instance.pipeline = MagicMock(return_value=MockPipeline())

    
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