import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from backend.core.database import Base, get_db
from backend.app.main import app
from backend.models import User, Wallet, Ticker, MarketType, Currency
import uuid

# 1. 테스트용 DB (SQLite In-Memory)
# 나중에 Postgres로 바꾸려면 이 URL만 변경하면 됨
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 2. DB Fixture
@pytest.fixture(scope="function")
def db_session():
    """
    각 테스트 함수마다 새로운 DB 세션을 생성하고,
    테스트가 끝나면 롤백/삭제하여 격리된 환경을 제공함.
    """
    # 테이블 생성
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

# 3. Client Fixture (API 호출용)
@pytest.fixture(scope="function")
def client(db_session):
    """
    FastAPI의 get_db 의존성을 테스트용 DB 세션으로 덮어쓰기(Override)
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as c:
        yield c
    
    app.dependency_overrides.clear()

# 4. 테스트 데이터 Fixture (유저, 코인)
@pytest.fixture(scope="function")
def test_user(db_session):
    user_id = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6")
    # User 모델이 필요하다면 생성 (현재 코드상 User 모델 의존성이 약하면 생략 가능하나, 정석대로 생성)
    # User 테이블이 있다면 생성
    try:
        user = User(id=user_id, email="test@test.com", hashed_password="pw", username="tester")
        db_session.add(user)
    except:
        pass # User 모델이 없을 수도 있음
        
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

# 5. Redis & RabbitMQ Mocking
@pytest.fixture(autouse=True)
def mock_external_services():
    """
    모든 테스트에 자동으로 적용됨.
    Redis와 RabbitMQ 연결을 가로채서 실제 연결을 시도하지 않게 함.
    """
    with patch("backend.app.routers.order.aio_pika.connect_robust") as mock_rabbit:
        # RabbitMQ Mock
        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_rabbit.return_value.__aenter__.return_value = mock_connection
        
        # Redis Mock (trade_service.py 등에서 사용)
        # 주의: 실제 로직 테스트 시 'get_current_price'를 개별적으로 patch해야 할 수도 있음.
        # 여기서는 연결 생성만 막음.
        with patch("redis.Redis") as mock_redis_cls:
            mock_redis_instance = MagicMock()
            mock_redis_cls.return_value = mock_redis_instance
            
            yield {
                "rabbitmq": mock_rabbit,
                "redis": mock_redis_instance
            }