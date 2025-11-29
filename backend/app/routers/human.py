from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from decimal import Decimal

from backend.core.database import get_db
from backend.core.deps import get_current_user_id
from backend.models import User, Ticker, Portfolio, MarketType, Currency, TickerSource

router = APIRouter(prefix="/human", tags=["human_etf"])

@router.post("/ipo")
async def create_ipo(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    [IPO] 자신의 지분을 주식으로 발행합니다.
    - HUMAN_{USER_ID} 티커 생성
    - 1,000주 발행하여 본인 지갑에 입고
    - 이미 발행했다면 에러
    """
    
    # 1. 이미 IPO 했는지 확인
    ticker_symbol = f"HUMAN_{user_id}"
    ticker_id = f"HUMAN-{user_id}"
    
    existing_ticker = await db.execute(select(Ticker).where(Ticker.id == ticker_id))
    if existing_ticker.scalars().first():
        raise HTTPException(status_code=400, detail="You have already listed your Human ETF.")
        
    # 2. 유저 정보 조회
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()
    
    # 3. Ticker 생성
    # 파산 상태 여부는 프론트엔드에서 처리하도록 백엔드 로직에서 제거
    ticker_name = f"{user.nickname}'s ETF"
        
    new_ticker = Ticker(
        id=ticker_id,
        symbol=ticker_symbol,
        name=ticker_name,
        market_type=MarketType.HUMAN,
        currency=Currency.KRW, # 인간 주식은 원화 거래
        source=TickerSource.UPBIT, # Source는 내부 시스템이므로 MOCK이나 TEST가 맞지만, 일단 UPBIT 구조 따름 (추후 TickerSource.INTERNAL 추가 고려)
        is_active=True
    )
    db.add(new_ticker)
    
    # 4. 주식 발행 (본인 포트폴리오에 추가)
    # 평단가는 0원 (무에서 유를 창조)
    ipo_quantity = Decimal("1000")
    
    portfolio = Portfolio(
        user_id=user_id,
        ticker_id=ticker_id,
        quantity=ipo_quantity,
        average_price=Decimal("0")
    )
    db.add(portfolio)
    
    await db.commit()
    
    return {"message": f"Successfully listed {ticker_symbol}. 1,000 shares issued.", "ticker_id": ticker_id}
