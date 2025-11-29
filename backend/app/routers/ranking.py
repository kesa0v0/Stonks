from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional
from pydantic import BaseModel

from backend.core.database import get_db
from backend.models import UserPersona, User

router = APIRouter(prefix="/rankings", tags=["ranking"])

class RankingEntry(BaseModel):
    rank: int
    nickname: str
    value: float
    extra_info: Optional[dict] = None

@router.get("/{ranking_type}", response_model=List[RankingEntry])
async def get_rankings(
    ranking_type: str,
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
    """
    
    stmt = select(UserPersona, User).join(User, UserPersona.user_id == User.id)
    
    if ranking_type == "pnl":
        stmt = stmt.order_by(desc(UserPersona.total_realized_pnl))
    elif ranking_type == "loss":
        stmt = stmt.order_by(desc(UserPersona.total_loss))
    elif ranking_type == "volume":
        stmt = stmt.order_by(desc(UserPersona.total_trade_count))
    elif ranking_type == "fees":
        stmt = stmt.order_by(desc(UserPersona.total_fees_paid))
    elif ranking_type == "night":
        stmt = stmt.order_by(desc(UserPersona.night_trade_count))
    elif ranking_type == "win_rate":
        # 승률 계산은 DB에서 바로 정렬하기 까다로울 수 있음 (나눗셈).
        # 여기서는 간단히 win_count 내림차순으로 하거나, Python에서 정렬.
        # 데이터가 많지 않다면 가져와서 정렬하는 게 나음.
        # 최소 거래 횟수 필터링
        stmt = stmt.where(UserPersona.total_trade_count >= 10)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown ranking type: {ranking_type}")
    
    # win_rate 제외하고는 limit 적용
    if ranking_type != "win_rate":
        stmt = stmt.limit(limit)
        
    result = await db.execute(stmt)
    rows = result.all()
    
    rankings = []
    
    if ranking_type == "win_rate":
        # 메모리 정렬
        temp_list = []
        for persona, user in rows:
            if persona.total_trade_count > 0:
                rate = (persona.win_count / persona.total_trade_count) * 100
                temp_list.append((rate, user.nickname, persona))
        
        # 승률 내림차순 -> 거래횟수 내림차순
        temp_list.sort(key=lambda x: (x[0], x[2].total_trade_count), reverse=True)
        temp_list = temp_list[:limit]
        
        for i, (rate, nickname, persona) in enumerate(temp_list):
            rankings.append(RankingEntry(
                rank=i+1,
                nickname=nickname,
                value=round(rate, 2),
                extra_info={"trade_count": persona.total_trade_count}
            ))
    else:
        for i, (persona, user) in enumerate(rows):
            val = 0
            if ranking_type == "pnl": val = float(persona.total_realized_pnl)
            elif ranking_type == "loss": val = float(persona.total_loss)
            elif ranking_type == "volume": val = float(persona.total_trade_count)
            elif ranking_type == "fees": val = float(persona.total_fees_paid)
            elif ranking_type == "night": val = float(persona.night_trade_count)
            
            rankings.append(RankingEntry(
                rank=i+1,
                nickname=user.nickname,
                value=val
            ))
            
    return rankings
