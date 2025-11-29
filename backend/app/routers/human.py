from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from decimal import Decimal

from backend.core.database import get_db
from backend.core.deps import get_current_user_id
from backend.models import User, Ticker, Portfolio, MarketType, Currency, TickerSource
from backend.schemas.human import IpoCreate, BurnCreate

router = APIRouter(prefix="/human", tags=["human_etf"])

@router.post("/ipo")
async def create_ipo(
    ipo_in: IpoCreate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
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
        raise HTTPException(status_code=400, detail="You have already listed your Human ETF.")
        
    # 2. 유저 정보 조회
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()
    
    # 파산자 배당률 체크
    if user.is_bankrupt and ipo_in.dividend_rate < 0.5:
        raise HTTPException(status_code=400, detail="Bankrupt users must set dividend rate to at least 50%.")

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

@router.post("/burn")
async def burn_shares(
    burn_in: BurnCreate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
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
        raise HTTPException(status_code=400, detail="Insufficient shares to burn.")
        
    # 2. 차감
    portfolio.quantity -= burn_qty
    
    # 0이면 삭제
    if portfolio.quantity <= Decimal("1e-8"):
        await db.delete(portfolio)
        # Flush to ensure deletion is counted in next query
        await db.flush() 
        
    # 3. 전체 유통량 확인 (해방 조건)
    # 현재 DB에 남아있는 모든 Portfolio의 quantity 합계
    total_shares_stmt = select(func.sum(Portfolio.quantity)).where(Portfolio.ticker_id == ticker_id)
    total_res = await db.execute(total_shares_stmt)
    total_shares = total_res.scalar() or Decimal(0)
    
    is_delisted = False
    if total_shares <= Decimal("1e-8"):
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
