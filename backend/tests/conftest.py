import pytest
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock, patch 
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
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


# 1. 테스트용 DB (SQLite In-Memory with aiosqlite)
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
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
    # 테이블 생성
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with TestingSessionLocal() as session:
        yield session
        
    # 테이블 삭제 (cleanup)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

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