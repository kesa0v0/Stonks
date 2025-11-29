import json
import redis.asyncio as async_redis
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import date, datetime, time, timezone
from uuid import UUID

from backend.core.database import get_db
from backend.core.deps import get_current_user_id
from backend.core.cache import get_redis
from backend.models import Order, User, Wallet, Portfolio, Ticker
from backend.core.enums import OrderStatus
from backend.schemas.portfolio import PnLResponse, PortfolioResponse, AssetResponse

router = APIRouter(prefix="/me", tags=["me"])

@router.get("/portfolio", response_model=PortfolioResponse)
async def get_my_portfolio(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    redis: async_redis.Redis = Depends(get_redis)
):
    """
    내 포트폴리오(보유 자산 및 현금)를 조회합니다.
    """
    # 1. 지갑(현금) 조회
    wallet_result = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
    wallet = wallet_result.scalars().first()
    cash_balance = float(wallet.balance) if wallet else 0.0

    # 2. 보유 주식 조회 (Ticker 정보 조인)
    # N+1 문제를 방지하기 위해 조인 사용
    stmt = (
        select(Portfolio, Ticker)
        .outerjoin(Ticker, Portfolio.ticker_id == Ticker.id)
        .where(Portfolio.user_id == user_id)
    )
    result = await db.execute(stmt)
    rows = result.all()
    
    assets = []
    total_position_value = 0.0

    for portfolio, ticker in rows:
        # Redis에서 현재가 조회 (Async)
        price_data = await redis.get(f"price:{portfolio.ticker_id}")
        current_price = 0.0
        if price_data:
            current_price = float(json.loads(price_data)['price'])
        else:
            # 시세가 없으면 평단가로 가정
            current_price = float(portfolio.average_price)

        qty = float(portfolio.quantity)
        avg_price = float(portfolio.average_price)
        
        # 평가 금액 (Valuation) 및 매입 원금 (Cost Basis)
        # 숏 포지션(qty < 0)일 경우 둘 다 음수
        valuation = qty * current_price
        cost_basis = qty * avg_price
        
        total_position_value += valuation
        
        # 수익률 계산 (Long/Short 통합 공식)
        # PnL = Valuation - Cost Basis
        # Rate = PnL / abs(Cost Basis)
        profit_rate = 0.0
        if abs(cost_basis) > 0:
            profit_rate = ((valuation - cost_basis) / abs(cost_basis)) * 100

        assets.append(AssetResponse(
            ticker_id=portfolio.ticker_id,
            symbol=ticker.symbol if ticker else "UNKNOWN",
            name=ticker.name if ticker else "Unknown",
            quantity=qty,
            average_price=avg_price,
            current_price=current_price,
            total_value=valuation,
            profit_rate=round(profit_rate, 2)
        ))

    # 총 자산 = 현금 + 포지션 평가액(숏은 음수이므로 자동 차감됨)
    return {
        "cash_balance": cash_balance,
        "total_asset_value": cash_balance + total_position_value,
        "assets": assets
    }

@router.get("/pnl", response_model=PnLResponse)
async def get_my_pnl(
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    특정 기간 동안의 실현 손익(Realized PnL) 합계를 조회합니다.
    """
    # 날짜 -> DateTime 변환 (UTC 기준)
    # start: 해당 일의 00:00:00
    # end: 해당 일의 23:59:59.999999
    
    # 주의: DB의 filled_at은 timezone=True (UTC)임.
    # 클라이언트가 보낸 날짜를 UTC로 간주하거나, KST로 간주해서 변환해야 함.
    # 여기선 단순하게 UTC 기준으로 00:00~23:59로 처리.
    
    start_dt = datetime.combine(start, time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end, time.max).replace(tzinfo=timezone.utc)
    
    stmt = select(func.sum(Order.realized_pnl)).where(
        and_(
            Order.user_id == user_id,
            Order.status == OrderStatus.FILLED,
            Order.filled_at >= start_dt,
            Order.filled_at <= end_dt
        )
    )
    
    result = await db.execute(stmt)
    total_pnl = result.scalar() or 0.0
    
    return PnLResponse(
        start_date=start,
        end_date=end,
        realized_pnl=float(total_pnl)
    )
