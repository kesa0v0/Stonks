from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc
from backend.models.season import Season
from backend.models.ranking import UserPersona
from backend.models.user import User, Wallet
from decimal import Decimal
from datetime import datetime
from backend.services.common.wallet import add_balance
from backend.core.constants import WALLET_REASON_SEASON_REWARD

async def get_active_season(db: AsyncSession) -> Season:
    """
    현재 활성화된 시즌을 반환합니다. 없으면 생성합니다.
    """
    stmt = select(Season).where(Season.is_active == True).order_by(Season.id.desc())
    result = await db.execute(stmt)
    season = result.scalars().first()
    
    if not season:
        # 시즌이 하나도 없으면 시즌 1 생성
        season = Season(name="Season 1", is_active=True)
        db.add(season)
        await db.commit()
        await db.refresh(season)
        
    return season

async def get_all_seasons(db: AsyncSession):
    """
    모든 시즌 정보를 반환합니다.
    """
    stmt = select(Season).order_by(Season.id.desc())
    result = await db.execute(stmt)
    return result.scalars().all()

async def reward_top_players(db: AsyncSession, season: Season):
    """
    시즌 종료 보상 지급
    - 수익금(PnL) 기준 상위 3명에게 뱃지와 상금 지급
    """
    # PnL 기준 상위 3명 조회
    stmt = (
        select(UserPersona, User, Wallet)
        .join(User, UserPersona.user_id == User.id)
        .join(Wallet, User.id == Wallet.user_id)
        .where(UserPersona.season_id == season.id)
        .order_by(desc(UserPersona.total_realized_pnl))
        .limit(3)
    )
    result = await db.execute(stmt)
    top_players = result.all()
    
    rewards = [
        {"rank": 1, "money": Decimal("10000000"), "badge": "Gold"},
        {"rank": 2, "money": Decimal("5000000"), "badge": "Silver"},
        {"rank": 3, "money": Decimal("3000000"), "badge": "Bronze"},
    ]
    
    for i, (persona, user, wallet) in enumerate(top_players):
        reward = rewards[i]
        
        # 1. 뱃지 지급
        new_badge = {
            "title": f"{season.name} {reward['badge']} Winner",
            "rank": reward['rank'],
            "season_id": season.id,
            "date": datetime.utcnow().isoformat()
        }
        # SQLAlchemy JSON field mutation requires explicit re-assignment or copy
        current_badges = list(user.badges) if user.badges else []
        current_badges.append(new_badge)
        user.badges = current_badges
        
        # 2. 상금 지급
        add_balance(wallet, reward['money'], WALLET_REASON_SEASON_REWARD)
        
        print(f"Reward: User {user.nickname} gets {reward['badge']} badge and {reward['money']} KRW")

async def end_current_season(db: AsyncSession):
    """
    현재 시즌을 종료하고 새로운 시즌을 시작합니다.
    """
    active_season = await get_active_season(db)
    
    # 보상 지급
    await reward_top_players(db, active_season)
    
    # 1. 현재 시즌 종료
    active_season.is_active = False
    active_season.end_date = datetime.utcnow()
    
    # 2. 새 시즌 생성
    next_id = active_season.id + 1
    new_season = Season(name=f"Season {next_id}", is_active=True)
    db.add(new_season)
    
    await db.commit()
    return new_season
