import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from backend.worker.candle_collector import save_candles_to_db, fetch_historical_candles, initial_seed
from backend.models import Candle, Ticker, MarketType, Currency
from backend.core.database import Base, engine

# DB 초기화 및 롤백을 위한 Fixture는 conftest.py에 있다고 가정하거나 여기서 간단히 정의
# 하지만 worker 테스트는 실제 DB보다는 로직 검증 위주이므로
# DB 세션을 사용하는 부분은 실제 DB(Test DB)를 쓰는 것이 좋음.

@pytest.mark.asyncio
async def test_save_candles_to_db(db_session):
    # 1. 준비 (Ticker 생성)
    ticker = Ticker(
        id="KRW-BTC", # ID 명시
        symbol="KRW-BTC", 
        market_type=MarketType.CRYPTO, 
        name="Bitcoin", 
        is_active=True,
        currency=Currency.KRW # Currency 명시
    )
    async with db_session as session:
        session.add(ticker)
        await session.commit()
        await session.refresh(ticker)

    # 2. 테스트 데이터 (CCXT OHLCV 포맷: [timestamp, open, high, low, close, volume])
    # 타임스탬프는 밀리세컨드
    ts_now = int(datetime.now(timezone.utc).timestamp() * 1000)
    ohlcv_data = [
        [ts_now, 100.0, 110.0, 90.0, 105.0, 1000.0],
        [ts_now - 60000, 95.0, 100.0, 90.0, 98.0, 500.0] # 1분 전
    ]

    # 3. 실행
    # 주의: save_candles_to_db 내부에서 AsyncSessionLocal()을 새로 호출함.
    # 테스트 환경에서는 이것을 db_session으로 오버라이드 해야 데이터가 공유됨.
    # 따라서 AsyncSessionLocal을 패치해야 함.
    
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__.return_value = db_session
    mock_session_maker.return_value.__aexit__.return_value = None
    
    # 이미 db_session은 async context manager가 아니므로(이미 열려있는 세션일 수 있음)
    # conftest.py의 db_session은 'yield session'을 하므로 그 자체는 세션 객체임.
    
    # 하지만 save_candles_to_db 코드는:
    # async with AsyncSessionLocal() as db:
    #     ...
    # 이렇게 되어 있으므로, AsyncSessionLocal()이 반환하는 객체가 __aenter__에서 db_session을 반환해야 함.

    with patch("backend.worker.candle_collector.AsyncSessionLocal", return_value=mock_session_maker.return_value):
        # 주의: mock_session_maker.return_value가 컨텍스트 매니저 역할.
        # __aenter__가 db_session을 리턴하도록 설정.
        mock_session_maker.return_value.__aenter__.return_value = db_session
        
        await save_candles_to_db(ohlcv_data, ticker, interval="1m")

    # 4. 검증
    # db_session은 외부에서 트랜잭션이 관리되거나 할 수 있으므로 바로 조회
    stmt = select(Candle).where(Candle.ticker_id == ticker.id).order_by(Candle.timestamp.desc())
    result = await db_session.execute(stmt)
    candles = result.scalars().all()

    assert len(candles) == 2
    assert candles[0].close == 105.0
    assert candles[0].volume == 1000.0
    assert candles[1].close == 98.0

@pytest.mark.asyncio
async def test_save_candles_upsert(db_session):
    """이미 존재하는 캔들이 업데이트(Upsert) 되는지 확인"""
    ticker = Ticker(
        id="KRW-ETH",
        symbol="KRW-ETH", 
        market_type=MarketType.CRYPTO, 
        name="Ethereum", 
        is_active=True,
        currency=Currency.KRW
    )
    # db_session을 사용하여 데이터 추가
    db_session.add(ticker)
    await db_session.commit()
    await db_session.refresh(ticker)

    ts_now = int(datetime.now(timezone.utc).timestamp() * 1000)
    
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__.return_value = db_session
    mock_session_maker.return_value.__aexit__.return_value = None

    with patch("backend.worker.candle_collector.AsyncSessionLocal", return_value=mock_session_maker.return_value):
        # 첫 번째 저장
        initial_data = [[ts_now, 100, 100, 100, 100, 100]]
        await save_candles_to_db(initial_data, ticker, interval="1m")

        # 두 번째 저장 (같은 시간, 값 변경)
        updated_data = [[ts_now, 200, 200, 200, 200, 200]]
        await save_candles_to_db(updated_data, ticker, interval="1m")

    stmt = select(Candle).where(Candle.ticker_id == ticker.id)
    result = await db_session.execute(stmt)
    candle = result.scalar_one()

    assert candle.close == 200 # 업데이트 되었어야 함
    assert candle.volume == 200

@pytest.mark.asyncio
async def test_initial_seed_skips_if_data_exists(db_session):
    """데이터가 이미 많으면 fetch_historical_candles를 호출하지 않는지 테스트"""
    
    # Mock 객체 설정
    mock_exchange = AsyncMock()
    mock_exchange.close = AsyncMock() 

    # Ticker 생성
    ticker = Ticker(
        id="KRW-XRP",
        symbol="KRW-XRP", 
        market_type=MarketType.CRYPTO, 
        name="Ripple", 
        is_active=True,
        currency=Currency.KRW
    )
    db_session.add(ticker)
    await db_session.commit()
    await db_session.refresh(ticker)

    # 가짜 데이터 1001개 생성
    base_time = datetime.now(timezone.utc)
    candles = []
    for i in range(1001):
        candles.append(Candle(
            ticker_id=ticker.id,
            timestamp=base_time - timedelta(days=i),
            interval='1d',
            open=100, high=100, low=100, close=100, volume=100
        ))
    
    db_session.add_all(candles)
    await db_session.commit()

    # AsyncSessionLocal 패치
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__.return_value = db_session
    mock_session_maker.return_value.__aexit__.return_value = None

    with patch("backend.worker.candle_collector.AsyncSessionLocal", return_value=mock_session_maker.return_value):
        with patch('backend.worker.candle_collector.fetch_historical_candles', new_callable=AsyncMock) as mock_fetch:
            with patch('backend.worker.candle_collector.fetch_and_store_candles', new_callable=AsyncMock): 
                # exchange argument가 필요하지만 initial_seed 내부에서 ccxt.upbit()를 호출하므로
                # ccxt.upbit()도 Mocking해야 함.
                with patch('ccxt.async_support.upbit', return_value=mock_exchange):
                     await initial_seed()
                
                # 검증: fetch_historical_candles가 호출되지 않았어야 함
                mock_fetch.assert_not_called()

@pytest.mark.asyncio
async def test_initial_seed_runs_if_data_insufficient(db_session):
    """데이터가 적으면 fetch_historical_candles를 호출하는지 테스트"""
    
    mock_exchange = AsyncMock()
    mock_exchange.close = AsyncMock()

    ticker = Ticker(
        id="KRW-ADA",
        symbol="KRW-ADA", 
        market_type=MarketType.CRYPTO, 
        name="Ada", 
        is_active=True,
        currency=Currency.KRW
    )
    db_session.add(ticker)
    await db_session.commit()
    
    # 데이터가 0개인 상태

    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__.return_value = db_session
    mock_session_maker.return_value.__aexit__.return_value = None

    with patch("backend.worker.candle_collector.AsyncSessionLocal", return_value=mock_session_maker.return_value):
        with patch('backend.worker.candle_collector.fetch_historical_candles', new_callable=AsyncMock) as mock_fetch:
            with patch('backend.worker.candle_collector.fetch_and_store_candles', new_callable=AsyncMock):
                 with patch('ccxt.async_support.upbit', return_value=mock_exchange):
                    await initial_seed()
                
                    # 검증: 호출되었어야 함
                    assert mock_fetch.call_count >= 1 
