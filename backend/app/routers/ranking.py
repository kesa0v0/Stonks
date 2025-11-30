from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from backend.core.database import get_db
from backend.schemas.ranking import RankingEntry, HallOfFameResponse
from backend.schemas.season import SeasonResponse
from backend.services.ranking_service import get_hall_of_fame_data, get_rankings_data
from backend.services.season_service import get_all_seasons

router = APIRouter(prefix="/rankings", tags=["ranking"])

@router.get("/seasons", response_model=List[SeasonResponse])
async def get_seasons(db: AsyncSession = Depends(get_db)):
    """
    모든 시즌 목록을 조회합니다.
    """
    return await get_all_seasons(db)

@router.get("/hall-of-fame", response_model=HallOfFameResponse)
async def get_hall_of_fame(db: AsyncSession = Depends(get_db)):
    """
    명예의 전당: 각 부문별 1위 유저를 모아서 반환합니다. (현재 활성 시즌 기준)
    """
    return await get_hall_of_fame_data(db)

@router.get("/{ranking_type}", response_model=List[RankingEntry])
async def get_rankings(
    ranking_type: str,
    season_id: int = Query(None, description="조회할 시즌 ID (생략 시 현재 활성 시즌)"),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """
    랭킹 조회 API
    - pnl: 실현 손익 순 (고수)
    - loss: 실현 손실 순 (흑우 - total_loss 내림차순)
    - volume: 거래 횟수 순 (단타왕)
    - win_rate: 승률 순 (익절/전체, 10회 이상 거래자만)
    - fees: 수수료 기부왕
    - night: 야행성 (미장 좀비)
    - profit_factor: 손익비 (총수익/총손실)
    - market_ratio: 성격 급한 정도 (시장가비율)
    """
    # 유효성 검사 (Router에서 담당)
    valid_types = ["pnl", "loss", "volume", "fees", "night", "win_rate", "profit_factor", "market_ratio"]
    if ranking_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Unknown ranking type: {ranking_type}")

    return await get_rankings_data(db, ranking_type, limit, season_id=season_id)
