import json
from uuid import UUID
from datetime import date, datetime, time, timezone
from typing import List, Dict, Optional, Any
import redis.asyncio as async_redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update, delete

from backend.core import constants
from backend.core.exceptions import OrderNotFoundError, PermissionDeniedError, BankruptcyNotAllowedError, UserNotFoundError
from backend.models import User, Wallet, Portfolio, Ticker, Order, MarketType, Currency, TickerSource
from backend.schemas.portfolio import PortfolioResponse, AssetResponse, PnLResponse
from backend.schemas.order import OrderResponse
from backend.schemas.user import UserProfileResponse # Import new schema
from backend.core.enums import OrderStatus
from backend.services.common.asset import liquidate_user_assets
from backend.services.common.price import get_current_price

async def get_user_portfolio(
    db: AsyncSession, 
    user_id: UUID, 
    redis: async_redis.Redis
) -> PortfolioResponse:
    """
    내 포트폴리오(보유 자산 및 현금)를 조회합니다.
    """
    # 1. 지갑(현금) 조회
    wallet_result = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
    wallet = wallet_result.scalars().first()
    cash_balance = float(wallet.balance) if wallet else 0.0

    # 2. 보유 주식 조회 (Ticker 정보 + 전일 종가 조인)
    # Latest 1d candle subquery for previous close
    from backend.models.candle import Candle
    from sqlalchemy.orm import aliased
    
    prev_stmt = (
        select(Candle)
        .where(Candle.interval == '1d')
        .distinct(Candle.ticker_id)
        .order_by(Candle.ticker_id, Candle.timestamp.desc())
        .subquery()
    )
    prev = aliased(Candle, prev_stmt)

    stmt = (
        select(Portfolio, Ticker, prev)
        .outerjoin(Ticker, Portfolio.ticker_id == Ticker.id)
        .outerjoin(prev, Portfolio.ticker_id == prev.ticker_id)
        .where(Portfolio.user_id == user_id)
    )
    result = await db.execute(stmt)
    rows = result.all()
    
    assets = []
    total_position_value = 0.0
    total_prev_position_value = 0.0

    for portfolio, ticker, prev_candle in rows:
        # Redis에서 현재가 조회 (Async)
        price_decimal = await get_current_price(redis, portfolio.ticker_id)
        current_price = float(price_decimal) if price_decimal else float(portfolio.average_price)

        qty = float(portfolio.quantity)
        avg_price = float(portfolio.average_price)
        
        # 평가 금액 (Valuation) 및 매입 원금 (Cost Basis)
        valuation = qty * current_price
        cost_basis = qty * avg_price
        
        total_position_value += valuation
        
        # Calculate previous value for 24h change
        # If prev_candle exists, use its close. Else fallback to current_price (no change) or cost?
        # Fallback to current_price means 0 change contribution from this asset.
        prev_price = float(prev_candle.close) if prev_candle else current_price
        total_prev_position_value += qty * prev_price
        
        # 수익률 계산
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

    total_asset_value = cash_balance + total_position_value
    
    # Calculate Total Portfolio Change %
    # We consider cash as stable (no change), so we include cash in the denominator?
    # Usually "Portfolio Change" implies the change in total value.
    # Prev Total Value = Cash (assumed const) + Prev Position Value
    total_prev_asset_value = cash_balance + total_prev_position_value
    
    total_asset_change_percent = 0.0
    if total_prev_asset_value > 0:
        total_asset_change_percent = ((total_asset_value - total_prev_asset_value) / total_prev_asset_value) * 100

    return {
        "cash_balance": cash_balance,
        "total_asset_value": total_asset_value,
        "total_asset_change_percent": f"{total_asset_change_percent:.2f}",
        "assets": assets
    }

async def get_user_pnl(
    db: AsyncSession, 
    user_id: UUID, 
    start: date, 
    end: date
) -> PnLResponse:
    """
    특정 기간 동안의 실현 손익(Realized PnL) 합계를 조회합니다.
    """
    # 날짜 -> DateTime 변환 (UTC 기준)
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

async def get_user_orders(db: AsyncSession, user_id: UUID, limit: int = 20) -> List[Order]:
    """
    내 전체 주문 내역을 조회합니다.
    """
    result = await db.execute(
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    orders = result.scalars().all()
    return orders

async def get_user_open_orders(db: AsyncSession, user_id: UUID) -> List[Order]:
    """
    내 미체결(PENDING) 주문 내역을 조회합니다.
    """
    result = await db.execute(
        select(Order)
        .where(
            Order.user_id == user_id,
            Order.status == OrderStatus.PENDING
        )
        .order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()
    return orders

async def get_user_order_detail(db: AsyncSession, user_id: UUID, order_id: UUID) -> OrderResponse:
    """
    특정 주문의 상세 정보를 조회합니다. (본인 주문만 가능)
    """
    result = await db.execute(select(Order).where(Order.id == order_id))
    order_obj = result.scalars().first()

    if not order_obj:
        raise OrderNotFoundError("주문을 찾을 수 없습니다.")

    if str(order_obj.user_id) != str(user_id):
        raise PermissionDeniedError("권한이 없습니다.")

    return {
        "order_id": str(order_obj.id),
        "status": order_obj.status,
        "message": "", 
        "ticker_id": order_obj.ticker_id,
        "side": order_obj.side,
        "type": order_obj.type,
        "quantity": float(order_obj.quantity),
        "target_price": float(order_obj.target_price) if order_obj.target_price is not None else None,
        "price": float(order_obj.price) if order_obj.price is not None else None,
        "unfilled_quantity": float(order_obj.unfilled_quantity) if order_obj.unfilled_quantity is not None else None,
        "created_at": order_obj.created_at,
        "cancelled_at": order_obj.cancelled_at,
        "filled_at": order_obj.filled_at,
        "fail_reason": order_obj.fail_reason,
        "user_id": str(order_obj.user_id),
        "realized_pnl": float(order_obj.realized_pnl) if order_obj.realized_pnl is not None else None
    }

async def process_bankruptcy(
    db: AsyncSession, 
    user_id: UUID, 
    redis: async_redis.Redis,
    force: bool = False
):
    """
    [파산 신청]
    """
    # 0. 총 자산 평가 및 파산 조건 확인
    wallet_result = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
    wallet = wallet_result.scalars().first()
    cash_balance = float(wallet.balance) if wallet else 0.0

    total_position_value = 0.0
    stmt_portfolio = select(Portfolio).where(Portfolio.user_id == user_id)
    portfolios = (await db.execute(stmt_portfolio)).scalars().all()
    
    # Store prices for liquidation phase to avoid re-fetching
    portfolio_prices = {}
    for portfolio in portfolios:
        price_decimal = await get_current_price(redis, portfolio.ticker_id)
        current_price = float(price_decimal) if price_decimal else float(portfolio.average_price)
        
        total_position_value += float(portfolio.quantity) * current_price
        portfolio_prices[portfolio.ticker_id] = current_price
    
    total_asset_value = cash_balance + total_position_value
    
    if not force and total_asset_value > 0:
        raise BankruptcyNotAllowedError(total_asset_value, f"총 자산이 0 이하일 때만 파산 신청이 가능합니다. 현재 총 자산: {total_asset_value}")
        
    # 1. 미체결 주문 취소 처리
    await db.execute(
        update(Order)
        .where(
            and_(
                Order.user_id == user_id, 
                Order.status == OrderStatus.PENDING
            )
        )
        .values(
            status=OrderStatus.CANCELLED,
            cancelled_at=func.now(),
            fail_reason="Bankruptcy application"
        )
    )

    # Ensure wallet exists if it was None initially
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0)
        db.add(wallet)

    # 2. 보유 포트폴리오 시장가 청산 및 삭제
    await liquidate_user_assets(db, user_id, wallet, redis)

    # 3. 유저 정보 업데이트 (파산 상태, 횟수)
    user_stmt = select(User).where(User.id == user_id)
    user_res = await db.execute(user_stmt)
    user = user_res.scalars().first()
    
    user.is_bankrupt = True
    user.bankruptcy_count += 1

    # 4. HUMAN Ticker 확인 및 생성
    ticker_id = f"HUMAN-{user_id}"
    ticker_stmt = select(Ticker).where(Ticker.id == ticker_id)
    ticker = (await db.execute(ticker_stmt)).scalars().first()
    
    if not ticker:
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
    else:
        ticker.is_active = True
        # 닉네임 변경 반영
        ticker.name = f"{user.nickname}'s ETF"

    # 5. 주식 1,000주 발행 (본인 포트폴리오에 입고)
    new_portfolio = Portfolio(
        user_id=user_id,
        ticker_id=ticker_id,
        quantity=constants.HUMAN_STOCK_ISSUED_ON_BANKRUPTCY,
        average_price=0 # Cost Basis 0원으로 설정
    )
    db.add(new_portfolio)

    await db.commit()
    
    # Refresh wallet to get the updated balance after liquidation
    await db.refresh(wallet)

    return {
        "message": "Bankruptcy filed. Assets liquidated.",
        "balance": wallet.balance,
        "is_bankrupt": True,
        "human_stock_issued": constants.HUMAN_STOCK_ISSUED_ON_BANKRUPTCY
    }

async def get_user_profile(
    db: AsyncSession,
    user_id: UUID
) -> UserProfileResponse:
    """
    특정 유저의 프로필 정보 (닉네임, 뱃지, 수익률 등)를 조회합니다.
    """
    user_result = await db.execute(
        select(User)
        .where(User.id == user_id)
    )
    user = user_result.scalars().first()

    if not user:
        raise UserNotFoundError("User not found.")

    # Calculate profit rate for all time
    start_date = user.created_at.date() if user.created_at else date(2020, 1, 1) # Fallback to a very old date
    end_date = date.today()

    pnl_response = await get_user_pnl(db, user_id, start_date, end_date)
    
    # Placeholder for profit_rate calculation
    # In a real system, this would be a more sophisticated calculation
    # involving initial capital, deposits, withdrawals, and current portfolio value.
    # For now, let's use a simplified approach for demonstration.
    # Assuming an arbitrary initial capital for ROI calculation.
    initial_capital_for_roi_calc = 1_000_000 # Example: 1 million KRW starting capital (hypothetical)

    profit_rate_percent = None
    if pnl_response.realized_pnl is not None and initial_capital_for_roi_calc > 0:
        profit_rate_percent = (pnl_response.realized_pnl / initial_capital_for_roi_calc) * 100
        profit_rate_percent = f"{profit_rate_percent:.2f}" # Format to two decimal places

    return UserProfileResponse(
        id=user.id,
        nickname=user.nickname,
        badges=user.badges or [], # Ensure it's a list even if DB returns None
        profit_rate=profit_rate_percent
    )
