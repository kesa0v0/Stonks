# backend/app/routers/portfolio.py
import json
import redis
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.core.database import get_db
from backend.core.config import settings
from backend.models import User, Wallet, Portfolio, Ticker
from backend.schemas.portfolio import PortfolioResponse, AssetResponse

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# Redis 연결 (시세 조회용)
r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)

# 테스트용 고정 유저 ID (나중에 Auth 붙이면 교체)
TEST_USER_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

@router.get("/", response_model=PortfolioResponse)
def get_my_portfolio(db: Session = Depends(get_db)):
    # 1. 지갑(현금) 조회
    wallet = db.query(Wallet).filter(Wallet.user_id == TEST_USER_ID).first()
    cash_balance = float(wallet.balance) if wallet else 0.0

    # 2. 보유 주식 조회
    portfolios = db.query(Portfolio).filter(Portfolio.user_id == TEST_USER_ID).all()
    
    assets = []
    total_stock_value = 0.0

    for p in portfolios:
        # 종목 정보 가져오기 (Lazy Loading 방지용 join 권장하지만, 간단히 접근)
        ticker = db.query(Ticker).filter(Ticker.id == p.ticker_id).first()
        
        # Redis에서 현재가 조회
        price_data = r.get(f"price:{p.ticker_id}")
        current_price = 0.0
        if price_data:
            current_price = float(json.loads(price_data)['price'])
        else:
            # 시세가 없으면 평단가로 가정 (또는 0)
            current_price = float(p.average_price)

        qty = float(p.quantity)
        avg_price = float(p.average_price)
        
        # 평가 금액 & 수익률 계산
        valuation = qty * current_price
        total_stock_value += valuation
        
        profit_rate = 0.0
        if avg_price > 0:
            profit_rate = ((current_price - avg_price) / avg_price) * 100

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

    return {
        "cash_balance": cash_balance,
        "total_asset_value": cash_balance + total_stock_value,
        "assets": assets
    }