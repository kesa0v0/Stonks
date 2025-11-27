# backend/app/routers/portfolio.py
import json
import redis.asyncio as async_redis
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.core.database import get_db
from backend.core.config import settings
from backend.models import User, Wallet, Portfolio, Ticker
from backend.schemas.portfolio import PortfolioResponse, AssetResponse
from backend.core.deps import get_current_user_id
from backend.core.cache import get_redis

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

@router.get("", response_model=PortfolioResponse)
async def get_my_portfolio(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    redis: async_redis.Redis = Depends(get_redis)
):
    # 1. 지갑(현금) 조회
    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
    cash_balance = float(wallet.balance) if wallet else 0.0

    # 2. 보유 주식 조회
    portfolios = db.query(Portfolio).filter(Portfolio.user_id == user_id).all()
    
    assets = []
    total_position_value = 0.0

    for p in portfolios:
        # 종목 정보 가져오기
        ticker = db.query(Ticker).filter(Ticker.id == p.ticker_id).first()
        
        # Redis에서 현재가 조회 (Async)
        price_data = await redis.get(f"price:{p.ticker_id}")
        current_price = 0.0
        if price_data:
            current_price = float(json.loads(price_data)['price'])
        else:
            # 시세가 없으면 평단가로 가정
            current_price = float(p.average_price)

        qty = float(p.quantity)
        avg_price = float(p.average_price)
        
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
            ticker_id=p.ticker_id,
            symbol=ticker.symbol if ticker else "UNKNOWN",
            name=ticker.name if ticker else "Unknown",
            quantity=qty,
            average_price=avg_price,
            current_price=current_price,
            total_value=valuation,
            profit_rate=round(profit_rate, 2)
        ))

    # 총 자산 = 현금 + 포지션 평가액(숏은 음수이므로 자동 차감됨)
    # 예: 현금 200, 숏 평가액 -110 (빌려서 판 돈 100 포함된 현금 상태에서 갚아야 할 돈 -110) -> 순자산 90
    return {
        "cash_balance": cash_balance,
        "total_asset_value": cash_balance + total_position_value,
        "assets": assets
    }