from decimal import Decimal
import random
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.core import constants
from backend.core.exceptions import (
    BailoutNotAllowedError, 
    NoSharesToBailoutError, 
    HumanETFAlreadyListedError, 
    InvalidDividendRateError, 
    InsufficientSharesToBurnError
)
from backend.models import User, Ticker, Portfolio, MarketType, Currency, TickerSource, Wallet
from backend.schemas.human import IpoCreate, BurnCreate
from backend.services.common.wallet import add_balance
from backend.core.constants import WALLET_REASON_HUMAN_DISTRIBUTION

async def process_bailout(db: AsyncSession, user_id: UUID):
    """
    [긴급 구제 금융 신청]
    - 조건: 파산 상태이며, 발행한 Human ETF 주식이 팔리지 않음.
    - 효과: 시스템 봇이 평가 금액으로 전량 매수.
    - 평가 공식: 기본금 * (1 - 파산횟수 * 패널티) * 활동점수 * 랜덤운빨
    """
    # 1. 유저 및 파산 상태 확인
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()
    
    if not user or not user.is_bankrupt:
        raise BailoutNotAllowedError()

    ticker_id = f"HUMAN-{user_id}"

    # 2. 보유 주식 확인 (안 팔린 재고)
    stmt = select(Portfolio).where(
        Portfolio.user_id == user_id,
        Portfolio.ticker_id == ticker_id
    ).with_for_update()
    result = await db.execute(stmt)
    portfolio = result.scalars().first()

    if not portfolio or portfolio.quantity <= 0:
        raise NoSharesToBailoutError()

    # 3. 구제 금융 금액 산정 (The Evaluation)
    # 신용도 패널티 적용 (최대 90%까지만 깎임)
    penalty_factor = max(0.1, 1.0 - (user.bankruptcy_count * constants.HUMAN_BAILOUT_PENALTY_PER_COUNT))
    
    # 활동 점수 (임시: 1.0 ~ 1.2 랜덤)
    activity_bonus = random.uniform(1.0, 1.2)
    
    # 운빨 요소 (0.7 ~ 1.3)
    luck_factor = random.uniform(0.7, 1.3)
    
    # 총 매입액 계산
    total_bailout = constants.HUMAN_BAILOUT_BASE_AMOUNT * penalty_factor * activity_bonus * luck_factor
    total_bailout = round(total_bailout) # 정수 반올림
    
    # 최소 보장액 (주당 10원)
    min_guarantee = float(portfolio.quantity) * 10
    final_amount = max(total_bailout, min_guarantee)
    
    # 4. 주식 매수 (시스템이 소각 처리한다고 가정 -> 삭제)
    qty = portfolio.quantity
    await db.delete(portfolio)
    
    # 5. 지갑 입금
    wallet_stmt = select(Wallet).where(Wallet.user_id == user_id).with_for_update()
    wallet_res = await db.execute(wallet_stmt)
    wallet = wallet_res.scalars().first()
    
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0)
        db.add(wallet)
        
    add_balance(wallet, Decimal(final_amount), WALLET_REASON_HUMAN_DISTRIBUTION)
    
    await db.commit()
    
    return {
        "message": "Bailout successful. System bought your shares.",
        "sold_quantity": qty,
        "bailout_amount": final_amount,
        "factors": {
            "base": constants.HUMAN_BAILOUT_BASE_AMOUNT,
            "penalty_factor": round(penalty_factor, 2),
            "activity_bonus": round(activity_bonus, 2),
            "luck_factor": round(luck_factor, 2)
        }
    }

async def process_ipo(db: AsyncSession, user_id: UUID, ipo_in: IpoCreate):
    """
    [IPO] 자신의 지분을 주식으로 발행합니다.
    - HUMAN_{USER_ID} 티커 생성
    - 입력받은 수량만큼 발행하여 본인 지갑에 입고
    - 파산자는 배당률 50% 이상 필수
    """
    
    # 1. 이미 IPO 했는지 확인
    ticker_id = f"HUMAN-{user_id}"
    existing_ticker = await db.execute(select(Ticker).where(Ticker.id == ticker_id))
    if existing_ticker.scalars().first():
        raise HumanETFAlreadyListedError()
        
    # 2. 유저 정보 조회
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()
    
    # 파산자 배당률 체크
    if user.is_bankrupt and ipo_in.dividend_rate < constants.HUMAN_DIVIDEND_RATE_MIN:
        raise InvalidDividendRateError()

    # 배당률 업데이트
    user.dividend_rate = Decimal(str(ipo_in.dividend_rate))
    
    # 3. Ticker 생성
    ticker_symbol = f"HUMAN_{user_id}"
    ticker_name = f"{user.nickname}'s ETF"
        
    new_ticker = Ticker(
        id=ticker_id,
        symbol=ticker_symbol,
        name=ticker_name,
        market_type=MarketType.HUMAN,
        currency=Currency.KRW,
        source=TickerSource.UPBIT, 
        is_active=True
    )
    db.add(new_ticker)
    
    # 4. 주식 발행 (본인 포트폴리오에 추가)
    portfolio = Portfolio(
        user_id=user_id,
        ticker_id=ticker_id,
        quantity=Decimal(str(ipo_in.quantity)),
        average_price=Decimal(str(ipo_in.initial_price))
    )
    db.add(portfolio)
    
    await db.commit()
    
    return {
        "message": f"Successfully listed {ticker_symbol}. {ipo_in.quantity} shares issued.", 
        "ticker_id": ticker_id,
        "dividend_rate": ipo_in.dividend_rate
    }

async def process_burn(db: AsyncSession, user_id: UUID, burn_in: BurnCreate):
    """
    [소각] 보유한 자사주(Human ETF)를 소각합니다.
    - 모든 유통 주식을 소각하면 상장 폐지 및 파산 해제(해방)됩니다.
    """
    ticker_id = f"HUMAN-{user_id}"
    
    # 1. 보유량 확인
    stmt = select(Portfolio).where(
        Portfolio.user_id == user_id,
        Portfolio.ticker_id == ticker_id
    ).with_for_update()
    result = await db.execute(stmt)
    portfolio = result.scalars().first()
    
    burn_qty = Decimal(str(burn_in.quantity))
    
    if not portfolio or portfolio.quantity < burn_qty:
        raise InsufficientSharesToBurnError()
        
    # 2. 차감
    portfolio.quantity -= burn_qty
    
    # 0이면 삭제
    if portfolio.quantity <= constants.HUMAN_BURN_THRESHOLD:
        await db.delete(portfolio)
        # Flush to ensure deletion is counted in next query
        await db.flush() 
        
    # 3. 전체 유통량 확인 (해방 조건)
    # 현재 DB에 남아있는 모든 Portfolio의 quantity 합계
    total_shares_stmt = select(func.sum(Portfolio.quantity)).where(Portfolio.ticker_id == ticker_id)
    total_res = await db.execute(total_shares_stmt)
    total_shares = total_res.scalar() or Decimal(0)
    
    is_delisted = False
    if total_shares <= constants.HUMAN_DELIST_THRESHOLD:
        # 해방!
        is_delisted = True
        
        # 유저 파산 해제
        user_stmt = select(User).where(User.id == user_id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalars().first()
        user.is_bankrupt = False
        
        # 티커 비활성화
        ticker_stmt = select(Ticker).where(Ticker.id == ticker_id)
        ticker_res = await db.execute(ticker_stmt)
        ticker = ticker_res.scalars().first()
        if ticker:
            ticker.is_active = False
            
    await db.commit()
    
    return {
        "message": f"Burned {burn_qty} shares.",
        "remaining_shares": portfolio.quantity if portfolio and portfolio.quantity > 0 else 0,
        "is_delisted": is_delisted
    }
