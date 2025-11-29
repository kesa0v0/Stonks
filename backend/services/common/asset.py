from decimal import Decimal
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import redis.asyncio as async_redis

from backend.models import Portfolio, Wallet
from backend.services.common.price import get_current_price

async def liquidate_user_assets(
    db: AsyncSession, 
    user_id: UUID, 
    wallet: Wallet, 
    redis_client: async_redis.Redis
) -> Decimal:
    """
    유저의 모든 포트폴리오 자산을 시장가로 청산하고, 그 수익을 지갑에 추가합니다.
    """
    total_proceeds = Decimal("0")

    # 유저의 모든 포트폴리오 조회
    stmt = select(Portfolio).where(Portfolio.user_id == user_id).with_for_update() # Lock for update
    portfolios = (await db.execute(stmt)).scalars().all()

    # 각 포트폴리오 아이템 청산
    for portfolio in portfolios:
        current_price = await get_current_price(redis_client, portfolio.ticker_id)
        if current_price is None:
            # 시세가 없으면 평단가로 가정
            current_price = portfolio.average_price
        
        proceeds = portfolio.quantity * current_price
        wallet.balance += proceeds
        total_proceeds += proceeds
        
        await db.delete(portfolio) # 포트폴리오 삭제

    return total_proceeds
