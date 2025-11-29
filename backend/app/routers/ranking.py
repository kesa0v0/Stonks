from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional, Dict
from pydantic import BaseModel

from backend.core.database import get_db
from backend.models import UserPersona, User

router = APIRouter(prefix="/rankings", tags=["ranking"])

class RankingEntry(BaseModel):
    rank: int
    nickname: str
    value: float
    extra_info: Optional[dict] = None

class HallOfFameResponse(BaseModel):
    top_profit: Optional[RankingEntry] = None
    top_loss: Optional[RankingEntry] = None
    top_volume: Optional[RankingEntry] = None
    top_win_rate: Optional[RankingEntry] = None
    top_fees: Optional[RankingEntry] = None
    top_night: Optional[RankingEntry] = None

@router.get("/hall-of-fame", response_model=HallOfFameResponse)
async def get_hall_of_fame(db: AsyncSession = Depends(get_db)):
    """
    명예의 전당: 각 부문별 1위 유저를 모아서 반환합니다.
    """
    # 모든 유저 페르소나 조회 (데이터가 많아지면 개별 쿼리로 최적화 필요)
    stmt = select(UserPersona, User).join(User, UserPersona.user_id == User.id)
    result = await db.execute(stmt)
    rows = result.all()
    
    if not rows:
        return HallOfFameResponse()

    # Helper to create entry
    def make_entry(row, val, rank=1):
        return RankingEntry(rank=rank, nickname=row[1].nickname, value=val)

    # 1. Profit
    top_profit_row = max(rows, key=lambda r: r[0].total_realized_pnl)
    top_profit = make_entry(top_profit_row, float(top_profit_row[0].total_realized_pnl)) if top_profit_row[0].total_realized_pnl > 0 else None

    # 2. Loss
    top_loss_row = max(rows, key=lambda r: r[0].total_loss)
    top_loss = make_entry(top_loss_row, float(top_loss_row[0].total_loss)) if top_loss_row[0].total_loss > 0 else None

    # 3. Volume
    top_volume_row = max(rows, key=lambda r: r[0].total_trade_count)
    top_volume = make_entry(top_volume_row, float(top_volume_row[0].total_trade_count)) if top_volume_row[0].total_trade_count > 0 else None

    # 4. Win Rate (최소 5회 이상 거래)
    eligible_win_rate = [r for r in rows if r[0].total_trade_count >= 5]
    top_win_rate = None
    if eligible_win_rate:
        top_wr_row = max(eligible_win_rate, key=lambda r: r[0].win_count / r[0].total_trade_count)
        rate = (top_wr_row[0].win_count / top_wr_row[0].total_trade_count) * 100
        top_win_rate = make_entry(top_wr_row, round(rate, 2))

    # 5. Fees
    top_fees_row = max(rows, key=lambda r: r[0].total_fees_paid)
    top_fees = make_entry(top_fees_row, float(top_fees_row[0].total_fees_paid)) if top_fees_row[0].total_fees_paid > 0 else None

    # 6. Night
    top_night_row = max(rows, key=lambda r: r[0].night_trade_count)
    top_night = make_entry(top_night_row, float(top_night_row[0].night_trade_count)) if top_night_row[0].night_trade_count > 0 else None

    return HallOfFameResponse(
        top_profit=top_profit,
        top_loss=top_loss,
        top_volume=top_volume,
        top_win_rate=top_win_rate,
        top_fees=top_fees,
        top_night=top_night
    )

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
    - profit_factor: 손익비 (총수익/총손실)
    - market_ratio: 성격 급한 정도 (시장가비율)
    """
    
    stmt = select(UserPersona, User).join(User, UserPersona.user_id == User.id)
    
    # DB 정렬 가능한 타입들
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
    elif ranking_type in ["win_rate", "profit_factor", "market_ratio"]:
        # Python 정렬 필요한 타입들: 필터링만 적용
        if ranking_type == "win_rate":
            stmt = stmt.where(UserPersona.total_trade_count >= 10)
        pass 
    else:
        raise HTTPException(status_code=400, detail=f"Unknown ranking type: {ranking_type}")
    
    # 계산형 랭킹은 전체 가져와서 정렬 (limit 미적용)
    if ranking_type not in ["win_rate", "profit_factor", "market_ratio"]:
        stmt = stmt.limit(limit)
        
    result = await db.execute(stmt)
    rows = result.all()
    
    rankings = []
    
    # --- 계산 및 정렬 로직 ---
    if ranking_type == "win_rate":
        temp_list = []
        for persona, user in rows:
            if persona.total_trade_count > 0:
                rate = (persona.win_count / persona.total_trade_count) * 100
                temp_list.append((rate, user.nickname, persona))
        temp_list.sort(key=lambda x: (x[0], x[2].total_trade_count), reverse=True)
        
        for i, (rate, nickname, persona) in enumerate(temp_list[:limit]):
            rankings.append(RankingEntry(rank=i+1, nickname=nickname, value=round(rate, 2), extra_info={"trade_count": persona.total_trade_count}))

    elif ranking_type == "profit_factor":
        temp_list = []
        for persona, user in rows:
            # 손실이 0이면 수익 그대로, 아니면 수익/손실
            loss = float(persona.total_loss)
            profit = float(persona.total_profit)
            if loss == 0:
                factor = profit if profit > 0 else 0
            else:
                factor = profit / loss
            temp_list.append((factor, user.nickname, profit, loss))
        
        temp_list.sort(key=lambda x: x[0], reverse=True)
        
        for i, (factor, nickname, p, l) in enumerate(temp_list[:limit]):
            rankings.append(RankingEntry(rank=i+1, nickname=nickname, value=round(factor, 2), extra_info={"profit": p, "loss": l}))

    elif ranking_type == "market_ratio":
        temp_list = []
        for persona, user in rows:
            if persona.total_trade_count > 0:
                ratio = (persona.market_order_count / persona.total_trade_count) * 100
                temp_list.append((ratio, user.nickname, persona.total_trade_count))
        
        temp_list.sort(key=lambda x: x[0], reverse=True)
        
        for i, (ratio, nickname, count) in enumerate(temp_list[:limit]):
            rankings.append(RankingEntry(rank=i+1, nickname=nickname, value=round(ratio, 2), extra_info={"trade_count": count}))

    else:
        # DB 정렬 완료된 경우
        for i, (persona, user) in enumerate(rows):
            val = 0
            if ranking_type == "pnl": val = float(persona.total_realized_pnl)
            elif ranking_type == "loss": val = float(persona.total_loss)
            elif ranking_type == "volume": val = float(persona.total_trade_count)
            elif ranking_type == "fees": val = float(persona.total_fees_paid)
            elif ranking_type == "night": val = float(persona.night_trade_count)
            
            rankings.append(RankingEntry(rank=i+1, nickname=user.nickname, value=val))
            
    return rankings
