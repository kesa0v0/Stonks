from decimal import Decimal
import random
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from fastapi import HTTPException
from typing import List

from backend.core import constants
from backend.core.exceptions import (
    BailoutNotAllowedError, 
    NoSharesToBailoutError, 
    HumanETFAlreadyListedError, 
    InvalidDividendRateError, 
    InsufficientSharesToBurnError
)
from backend.models import User, Ticker, Portfolio, MarketType, Currency, TickerSource, Wallet, DividendHistory, UserPersona # Added UserPersona
from backend.schemas.human import IpoCreate, BurnCreate, Shareholder, ShareholderResponse, DividendPaymentEntry, IssuerDividendStats, UpdateDividendRate, HumanCorporateValueResponse # Added HumanCorporateValueResponse
from backend.services.common.wallet import add_balance
from backend.core.constants import WALLET_REASON_HUMAN_DISTRIBUTION
from backend.core.event_hook import publish_event
import redis.asyncio as async_redis
from backend.core.config import settings
from sqlalchemy.orm import joinedload
from datetime import datetime
from backend.services.market_service import get_current_price_info # Added
from backend.services.season_service import get_active_season # Added

async def get_human_corporate_value(db: AsyncSession, redis_client: async_redis.Redis, user_id: UUID) -> HumanCorporateValueResponse:
    """
    [기업 가치 조회]
    발행자 본인의 Human ETF의 시장 가치 및 관련 지표를 조회합니다.
    """
    ticker_id = f"HUMAN-{user_id}"
    
    # 1. 현재 가격
    current_price = await get_current_price_info(redis_client, ticker_id)
    if current_price is None:
        # Ticker might not be active/price not updated
        return HumanCorporateValueResponse() 

    # 2. 총 발행 주식 수
    total_issued_stmt = select(func.sum(Portfolio.quantity)).where(Portfolio.ticker_id == ticker_id)
    total_issued_shares = (await db.execute(total_issued_stmt)).scalar_one_or_none() or Decimal(0)
    
    # 3. 시가총액 (Market Cap)
    market_cap = Decimal(str(current_price)) * total_issued_shares if total_issued_shares > 0 else Decimal(0)

    # 4. 최근 1일 평균 수익 (for PER) - 현재 시즌 PnL을 사용
    season = await get_active_season(db)
    user_persona_stmt = select(UserPersona.total_realized_pnl).where(
        UserPersona.user_id == user_id,
        UserPersona.season_id == season.id
    )
    total_realized_pnl_season = (await db.execute(user_persona_stmt)).scalar_one_or_none() or Decimal(0)

    per = None
    # PER = (주가) / (주당 순이익)
    # 여기서는 (현재 시가총액) / (총 순이익)으로 간주 (즉, 주당 순이익 대신 총 순이익 사용)
    # 더 정확하게는 (주가 / 주당 순이익)이 맞지만, Human ETF에서는 발행 주식 수가 가변적이고,
    # '주당 순이익'을 정의하기 모호하므로, 시총/총 순이익으로 간주.
    # 만약 total_realized_pnl_season이 0이면 PER 계산 불가
    if total_realized_pnl_season > 0:
        per = market_cap / total_realized_pnl_season
        # if per < 0: # PnL이 음수인데 MarketCap이 양수인 경우 -> 이 경우는 PER이 음수. 표시해도 됨.
        #     per = None # 의미 없는 값이므로 None 처리
    elif total_realized_pnl_season < 0 and market_cap > 0: # 수익이 음수일 때 PER
        per = Decimal('-1.0') # 음의 PER. -1.0으로 통일하거나 다른 방식으로 표시.
    
    return HumanCorporateValueResponse(
        current_price=str(current_price),
        market_cap=str(market_cap),
        per=str(per) if per is not None else None
    )

async def update_dividend_rate(db: AsyncSession, user_id: UUID, rate_in: UpdateDividendRate):
    """
    배당률을 변경합니다.
    - 파산자는 최소 배당률(50%) 제한이 있습니다.
    """
    user_stmt = select(User).where(User.id == user_id)
    user_res = await db.execute(user_stmt)
    user = user_res.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    new_rate = rate_in.dividend_rate
    
    # 배당률 체크
    if user.is_bankrupt:
        if new_rate < constants.HUMAN_DIVIDEND_RATE_MIN:
            raise InvalidDividendRateError()
    else:
        if new_rate < constants.HUMAN_DIVIDEND_RATE_NORMAL_MIN:
            raise InvalidDividendRateError()
        
    user.dividend_rate = new_rate
    await db.commit()
    
    return {
        "message": f"Dividend rate updated to {new_rate * 100}%",
        "dividend_rate": new_rate
    }

async def get_issuer_dividend_stats(db: AsyncSession, user_id: UUID) -> IssuerDividendStats:
    """
    발행자(나)의 배당 통계를 조회합니다.
    - 현재 배당률
    - 누적 배당 지급액
    """
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    cumulative_paid_stmt = (
        select(func.sum(DividendHistory.amount))
        .where(DividendHistory.payer_id == user_id)
    )
    cumulative_paid = (await db.execute(cumulative_paid_stmt)).scalar_one_or_none() or Decimal(0)

    return IssuerDividendStats(
        current_dividend_rate=str(user.dividend_rate),
        cumulative_paid_amount=str(cumulative_paid)
    )

async def get_issuer_dividend_history(db: AsyncSession, user_id: UUID, limit: int = 10) -> List[DividendPaymentEntry]:
    """
    발행자(나)의 최근 배당 지급 내역을 조회합니다.
    """
    history_stmt = (
        select(DividendHistory)
        .where(DividendHistory.payer_id == user_id)
        .order_by(DividendHistory.created_at.desc())
        .limit(limit)
    )
    history_result = await db.execute(history_stmt)
    histories = history_result.scalars().all()

    entries = []
    for h in histories:
        entries.append(DividendPaymentEntry(
            date=h.created_at,
            source_pnl="N/A", # Need to retrieve from a corresponding PnL record, which isn't directly in DividendHistory
            paid_amount=str(h.amount),
            ticker_id=h.ticker_id
        ))
    return entries

async def get_shareholders(db: AsyncSession, user_id: UUID) -> ShareholderResponse:
    """
    [주주 명부 조회]
    나의 Human ETF를 보유한 주주들의 목록을 반환합니다.
    """
    ticker_id = f"HUMAN-{user_id}"
    
    # 1. 모든 보유자 조회 (나 포함)
    stmt = (
        select(Portfolio)
        .options(joinedload(Portfolio.user))
        .where(
            Portfolio.ticker_id == ticker_id,
            Portfolio.quantity > 0
        )
    )
    result = await db.execute(stmt)
    portfolios = result.scalars().all()
    
    total_issued = sum(p.quantity for p in portfolios)
    my_holdings = next((p.quantity for p in portfolios if p.user_id == user_id), Decimal(0))
    
    # 2. 주주 리스트 구성 (나 제외)
    shareholders = []
    others = [p for p in portfolios if p.user_id != user_id]
    
    # 많이 가진 순 정렬
    others.sort(key=lambda p: p.quantity, reverse=True)
    
    for i, p in enumerate(others):
        pct = (float(p.quantity) / float(total_issued) * 100) if total_issued > 0 else 0
        shareholders.append(Shareholder(
            rank=i+1,
            nickname=p.user.nickname,
            quantity=str(p.quantity),
            percentage=round(pct, 2)
        ))
        
    return ShareholderResponse(
        total_issued=str(total_issued),
        my_holdings=str(my_holdings),
        shareholders=shareholders
    )

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

    # 이벤트 발행 (Human 채널용)
    try:
        redis_client = async_redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)
        event = {
            "type": "bailout_processed",
            "user_id": str(user_id),
            "nickname": user.nickname if user else str(user_id),
            "amount": float(final_amount),
        }
        await publish_event(redis_client, event, channel="human_events")
        await redis_client.close()
    except Exception:
        pass
    
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
    # 1. 유저 정보 조회
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()
    
    # 배당률 체크
    if user.is_bankrupt:
        if ipo_in.dividend_rate < constants.HUMAN_DIVIDEND_RATE_MIN:
            raise InvalidDividendRateError()
    else:
        if ipo_in.dividend_rate < constants.HUMAN_DIVIDEND_RATE_NORMAL_MIN:
            raise InvalidDividendRateError()

    # 배당률 업데이트
    user.dividend_rate = Decimal(str(ipo_in.dividend_rate))
    
    # 2. Ticker 확인 및 생성/갱신
    ticker_id = f"HUMAN-{user_id}"
    existing_ticker_result = await db.execute(select(Ticker).where(Ticker.id == ticker_id))
    ticker = existing_ticker_result.scalars().first()
    
    if ticker:
        if ticker.is_active:
            raise HumanETFAlreadyListedError()
        # 재상장
        ticker.is_active = True
        ticker.name = f"{user.nickname}'s ETF" # 닉네임 변경 반영
    else:
        # 신규 상장
        ticker = Ticker(
            id=ticker_id,
            symbol=f"HUMAN_{user_id}",
            name=f"{user.nickname}'s ETF",
            market_type=MarketType.HUMAN,
            currency=Currency.KRW,
            source=TickerSource.UPBIT, 
            is_active=True
        )
        db.add(ticker)
    
    # 3. 주식 발행 (본인 포트폴리오에 추가)
    # Check if portfolio exists (it shouldn't if burned, but handle cleanly)
    pf_stmt = select(Portfolio).where(Portfolio.user_id == user_id, Portfolio.ticker_id == ticker_id)
    pf_res = await db.execute(pf_stmt)
    portfolio = pf_res.scalars().first()

    issue_qty = Decimal(str(ipo_in.quantity))
    issue_price = Decimal(str(ipo_in.initial_price))

    if portfolio:
        portfolio.quantity += issue_qty
        # If effectively starting from 0, set average price to initial price
        if portfolio.quantity <= issue_qty + constants.HUMAN_BURN_THRESHOLD: # previously near 0
             portfolio.average_price = issue_price
    else:
        portfolio = Portfolio(
            user_id=user_id,
            ticker_id=ticker_id,
            quantity=issue_qty,
            average_price=issue_price
        )
        db.add(portfolio)
    
    await db.commit()

    # 이벤트 발행 (Human 채널용)
    try:
        redis_client = async_redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)
        event = {
            "type": "ipo_listed",
            "user_id": str(user_id),
            "symbol": f"HUMAN_{user_id}",
            "dividend_rate": float(ipo_in.dividend_rate),
        }
        await publish_event(redis_client, event, channel="human_events")
        await redis_client.close()
    except Exception:
        pass
    
    return {
        "message": f"Successfully listed fHUMAN_{user_id}. {ipo_in.quantity} shares issued.", 
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
