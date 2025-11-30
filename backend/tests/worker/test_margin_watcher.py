import pytest
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select

from backend.models import User, Wallet, Portfolio, Ticker, MarketType, Currency, TickerSource
from backend.services.liquidation_service import check_and_liquidate_user
from backend.core import constants

@pytest.mark.asyncio
async def test_margin_liquidation_trigger(db_session, mock_external_services):
    """
    숏 포지션 유저가 가격 상승으로 인해 청산 조건에 도달하면 강제 청산되는지 테스트
    """
    redis_client = mock_external_services["redis"]

    # 1. Setup User & Wallet
    user = User(email="short_squeezer@test.com", hashed_password="pw", nickname="shorty", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # 지갑: 100만원 보유
    wallet = Wallet(user_id=user.id, balance=Decimal("1000000"))
    db_session.add(wallet)
    
    # 2. Setup Ticker & Short Position
    ticker_id = "VOLATILE-COIN"
    ticker = Ticker(
        id=ticker_id, 
        symbol="VOLT", 
        name="Volatile", 
        market_type=MarketType.CRYPTO, 
        currency=Currency.KRW, 
        source=TickerSource.UPBIT, 
        is_active=True
    )
    db_session.add(ticker)
    
    # 숏 포지션: -100개 (진입가 10,000원 -> 숏 가치 1,000,000원)
    # 현재 지갑 100만원, 숏 부채 100만원 (가정). 순자산 = 100 + (-100*Price + 100*Avg) ?
    # 아니, Portfolio 모델엔 quantity, average_price만 있음.
    # 실제 매도 시 지갑에 돈이 들어옴.
    # 상황:
    # - 지갑: 2,000,000원 (원금 100만원 + 공매도 판 돈 100만원)
    # - 포트폴리오: -100개
    # - 현재가: 10,000원
    # - 평가:
    #   - 숏 부채: 100 * 10,000 = 1,000,000원
    #   - 순자산: 2,000,000 - 1,000,000 = 1,000,000원 (Safe)
    
    # 숏 쳤을 때 상황 재현
    wallet.balance = Decimal("2000000") 
    portfolio = Portfolio(
        user_id=user.id,
        ticker_id=ticker_id,
        quantity=Decimal("-100"),
        average_price=Decimal("10000")
    )
    db_session.add(portfolio)
    await db_session.commit()

    # 3. Price Spike (가격 급등) -> 청산 위기
    # 가격이 19,500원으로 오름.
    # - 숏 부채: 100 * 19,500 = 1,950,000원
    # - 순자산: 2,000,000 - 1,950,000 = 50,000원
    # - 유지 증거금: 1,950,000 * 0.05 = 97,500원
    # - 50,000 < 97,500 -> 청산 트리거 발동!
    
    spike_price = 19500
    await redis_client.set(f"price:{ticker_id}", f'{{"price": {spike_price}, "timestamp": 12345}}')

    # 4. Check Logic
    await check_and_liquidate_user(db_session, user.id, redis_client)
    
    # 5. Assertions
    await db_session.refresh(wallet)
    
    # 포트폴리오가 삭제되었어야 함 (청산됨)
    q = await db_session.execute(select(Portfolio).where(Portfolio.user_id == user.id))
    p = q.scalars().first()
    assert p is None, "Portfolio should be liquidated"
    
    # 잔액 확인: 2,000,000 - (100 * 19,500) = 50,000원 남아야 함
    # liquidate_user_assets는 시장가(19500)로 매수해서 갚음.
    # Buy 100 @ 19500 = 1,950,000 Cost.
    # Balance: 2,000,000 - 1,950,000 = 50,000. (수수료 제외 시)
    # 수수료 로직이 liquidate_user_assets -> place_order를 탄다면 적용되겠지만, 
    # liquidate_user_assets 구현을 보면 보통 직접 계산하거나 trade_service를 안탈 수도 있음.
    # backend/services/common/asset.py의 liquidate_user_assets를 확인해보면:
    # -> 직접 wallet balance 수정함. (수수료 고려 안되어있을 수 있음, 단순 차감)
    
    # 대략 5만원 근처인지 확인
    assert wallet.balance <= Decimal("60000")
    assert wallet.balance >= Decimal("40000")
