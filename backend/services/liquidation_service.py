import logging
from uuid import UUID
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import redis.asyncio as async_redis

from backend.core import constants
from backend.models import User, Portfolio, Wallet, Ticker
from backend.services.common.asset import liquidate_user_assets
from backend.services.common.price import get_current_price

logger = logging.getLogger(__name__)

async def check_and_liquidate_user(
    db: AsyncSession, 
    user_id: UUID, 
    redis_client: async_redis.Redis
):
    """
    특정 유저의 증거금 비율을 체크하고, 위험 수준이면 강제 청산합니다.
    """
    # 1. 유저 정보 및 지갑 조회
    wallet_stmt = select(Wallet).where(Wallet.user_id == user_id)
    wallet_res = await db.execute(wallet_stmt)
    wallet = wallet_res.scalars().first()
    
    if not wallet:
        return # 지갑도 없으면 패스 (이미 망했거나 초기화 전)

    # 2. 포트폴리오 전체 조회
    portfolio_stmt = select(Portfolio).where(Portfolio.user_id == user_id)
    portfolios = (await db.execute(portfolio_stmt)).scalars().all()
    
    if not portfolios:
        return # 포지션 없으면 패스

    # 3. 자산 평가 (Equity Calculation)
    cash_balance = Decimal(str(wallet.balance))
    
    long_value = Decimal("0")
    short_liability = Decimal("0") # 갚아야 할 돈 (양수)
    
    for p in portfolios:
        # 현재가 조회
        price = await get_current_price(redis_client, p.ticker_id)
        if price is None:
             # 가격 정보가 없으면 보수적으로 평단가 사용 혹은 스킵? 
             # 강제 청산에선 현재가가 중요하므로, 없을 경우 스킵하는게 안전할 수 있으나
             # 여기선 평단가라도 써서 계산 (Short squeeze 방지엔 취약함)
             price = p.average_price
        
        qty = p.quantity
        val = qty * price
        
        if qty > 0:
            long_value += val
        else:
            # 숏 포지션 가치 (음수) -> 부채로 계산
            short_liability += abs(val)
            
    # 순자산 (Net Equity) = 현금 + 롱 평가액 - 숏 부채
    net_equity = cash_balance + long_value - short_liability
    
    # 4. 마진 체크
    # 조건: 순자산 < 숏 부채 * 유지증거금율 (5%)
    # 즉, 숏 포지션을 커버하고도 5% 정도의 여유 자산이 없으면 위험
    
    # 숏 포지션이 없으면 청산 대상 아님
    if short_liability == 0:
        return

    maintenance_margin = short_liability * constants.MARGIN_MAINTENANCE_RATE
    
    if net_equity < maintenance_margin:
        logger.warning(f"🚨 [LIQUIDATION] User {user_id} triggered margin call. Equity: {net_equity}, Liability: {short_liability}")
        
        # 5. 강제 청산 실행
        await liquidate_user_assets(db, user_id, wallet, redis_client)
        
        # 추가: 알림 전송 로직 (추후 구현)이나 로그 기록
        # 유저 상태 업데이트? (파산 플래그는 안 세우고 포지션만 정리됨)
        # 잔고가 마이너스라면 0으로 보정해주거나 빚으로 남길지 결정. 
        # liquidate_user_assets는 단순 매도/매수만 하므로, 잔고가 마이너스 될 수 있음.
        # 시스템 보정: 마이너스면 0으로 채워줌? (대회니까 구제)
        if wallet.balance < 0:
            logger.info(f"User {user_id} balance negative ({wallet.balance}) -> Reset to 0 by system insurance.")
            wallet.balance = Decimal("0")
            
        await db.commit()
