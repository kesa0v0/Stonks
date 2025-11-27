import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from backend.core.database import Base, get_db
from backend.app.main import app
from backend.core.deps import get_current_user
from backend.models import User, Wallet, Ticker, MarketType, Currency
from backend.core.security import get_password_hash
import uuid

# 1. 테스트용 DB (SQLite In-Memory)
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 2. DB Fixture
@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

# 4. 테스트 데이터 Fixture (유저, 코인) - 먼저 정의
@pytest.fixture(scope="function")
def test_user(db_session):
    user_id = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6")
    
    # User 생성
    # 비밀번호 해시 적용
    hashed = get_password_hash("test1234")
    user = User(
        id=user_id, 
        email="test@test.com", 
        hashed_password=hashed, 
        nickname="Tester",
        is_active=True
    )
    db_session.add(user)
        
    # 지갑 생성
    wallet = Wallet(user_id=user_id, balance=100000000) # 1억
    db_session.add(wallet)
    db_session.commit()
    
    return user_id

@pytest.fixture(scope="function")
def test_ticker(db_session):
    ticker_id = "TEST-COIN"
    ticker = Ticker(
        id=ticker_id, 
        symbol="TEST/KRW", 
        name="Test Coin", 
        market_type=MarketType.CRYPTO,
        currency=Currency.KRW
    )
    db_session.add(ticker)
    db_session.commit()
    return ticker_id

# 3. Client Fixture (API 호출용)
@pytest.fixture(scope="function")
def client(db_session, test_user): # test_user가 먼저 생성되어야 함
    """
    FastAPI의 get_db 의존성을 테스트용 DB 세션으로 덮어쓰기(Override)
    또한 인증을 우회하기 위해 get_current_user를 덮어씀
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    def override_get_current_user():
        # test_user fixture가 생성한 유저를 반환
        return db_session.query(User).filter(User.id == test_user).first()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    
    with TestClient(app) as c:
        yield c
    
    app.dependency_overrides.clear()

# 5. Redis & RabbitMQ Mocking
@pytest.fixture(autouse=True)
def mock_external_services():
    with patch("backend.app.routers.order.aio_pika.connect_robust") as mock_rabbit:
        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_rabbit.return_value.__aenter__.return_value = mock_connection
        
        with patch("redis.Redis") as mock_redis_cls:
            mock_redis_instance = MagicMock()
            mock_redis_cls.return_value = mock_redis_instance
            yield {
                "rabbitmq": mock_rabbit,
                "redis": mock_redis_instance
            }
