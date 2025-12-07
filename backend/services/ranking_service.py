from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, case, Numeric
from datetime import datetime
from decimal import Decimal
import pytz
from typing import List

from backend.models import UserPersona, User, DividendHistory
from backend.core.enums import OrderType
from backend.schemas.ranking import RankingEntry, HallOfFameResponse
from backend.services.season_service import get_active_season

async def update_user_persona(
    db: AsyncSession, 
    user_id: str, 
    order_type: str, 
    pnl: Decimal = None, 
    fee: Decimal = 0
):
    """
    주문 체결 시 사용자의 페르소나(통계)를 업데이트합니다.
    """
    season = await get_active_season(db)
    
    stmt = select(UserPersona).where(
        UserPersona.user_id == user_id,
        UserPersona.season_id == season.id
    )
    result = await db.execute(stmt)
    persona = result.scalars().first()
    
    if not persona:
        # 명시적으로 초기값 할당하여 NoneType 에러 방지
        persona = UserPersona(
            user_id=user_id,
            season_id=season.id,
            total_trade_count=0,
            win_count=0,
            loss_count=0,
            total_realized_pnl=0,
            total_profit=0,
            total_loss=0,
            total_fees_paid=0,
            short_position_count=0,
            long_position_count=0,
            market_order_count=0,
            limit_order_count=0,
            night_trade_count=0,
            panic_sell_count=0,
            best_trade_pnl=0,
            worst_trade_pnl=0,
            top_buyer_count=0,
            bottom_seller_count=0
        )
        db.add(persona)
    
    # 1. 기본 카운터
    persona.total_trade_count += 1
    
    if order_type == OrderType.MARKET:
        persona.market_order_count += 1
    elif order_type == OrderType.LIMIT:
        persona.limit_order_count += 1
        
    persona.total_fees_paid += fee
    
    # 2. 시간대 체크 (UTC 17:00 ~ 20:00 = KST 02:00 ~ 05:00 = 미국 주식 좀비)
    # 현재 시간을 UTC로 변환
    now_utc = datetime.now(pytz.utc)
    
    if 17 <= now_utc.hour < 20:
        persona.night_trade_count += 1
        
    # 3. PnL 반영 (실현 손익이 있는 경우 = 청산 시)
    if pnl is not None:
        persona.total_realized_pnl += pnl
        
        if pnl > 0:
            persona.win_count += 1
            persona.total_profit += pnl
            
            # 인생 한방 (Best PnL)
            if pnl > persona.best_trade_pnl:
                persona.best_trade_pnl = pnl
                
        elif pnl < 0:
            persona.loss_count += 1
            persona.total_loss += abs(pnl) # 손실금은 양수로 누적
            
            # 지옥행 티켓 (Worst PnL - 음수 중 가장 작은 값)
            if pnl < persona.worst_trade_pnl:
                persona.worst_trade_pnl = pnl
    
    # 저장은 호출한 쪽(trade_service)의 트랜잭션에서 commit됨
    return persona

async def get_hall_of_fame_data(db: AsyncSession) -> HallOfFameResponse:
    """
    명예의 전당: 각 부문별 1위 유저를 모아서 반환합니다. (현재 시즌 기준)
    """
    season = await get_active_season(db)
    
    # 모든 유저 페르소나 조회 (데이터가 많아지면 개별 쿼리로 최적화 필요)
    stmt = select(UserPersona, User).join(User, UserPersona.user_id == User.id).where(UserPersona.season_id == season.id)
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

    # 7. Dividend King
    div_stmt = (
        select(DividendHistory.payer_id, func.sum(DividendHistory.amount).label("total_paid"), User.nickname)
        .join(User, DividendHistory.payer_id == User.id)
        .group_by(DividendHistory.payer_id, User.nickname)
        .order_by(desc("total_paid"))
        .limit(1)
    )
    div_result = await db.execute(div_stmt)
    div_row = div_result.first()
    
    top_dividend = None
    if div_row:
        _, total_paid, nickname = div_row
        if total_paid > 0:
            top_dividend = RankingEntry(rank=1, nickname=nickname, value=float(total_paid))

    return HallOfFameResponse(
        top_profit=top_profit,
        top_loss=top_loss,
        top_volume=top_volume,
        top_win_rate=top_win_rate,
        top_fees=top_fees,
        top_night=top_night,
        top_dividend=top_dividend
    )

async def get_rankings_data(
    db: AsyncSession,
    ranking_type: str,
    limit: int,
    season_id: int = None
) -> List[RankingEntry]:
    """
    랭킹 조회 로직
    """
    if season_id is None:
        season = await get_active_season(db)
        season_id = season.id

    stmt = select(UserPersona, User).join(User, UserPersona.user_id == User.id).where(UserPersona.season_id == season_id)
    
    # DB 정렬 가능한 타입들
    if ranking_type == "dividend":
        # Dividend History is separate from UserPersona
        stmt = (
            select(User.nickname, func.sum(DividendHistory.amount).label("total_paid"))
            .join(DividendHistory, User.id == DividendHistory.payer_id)
            .group_by(User.id, User.nickname)
            .order_by(desc("total_paid"))
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.all()
        
        rankings = []
        for i, (nickname, total_paid) in enumerate(rows):
            rankings.append(RankingEntry(rank=i+1, nickname=nickname, value=float(total_paid)))
        return rankings

    stmt = select(UserPersona, User).join(User, UserPersona.user_id == User.id).where(UserPersona.season_id == season_id)
    
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
        # Win Rate: (win_count / total_trade_count) * 100
        # Filter: min 10 trades
        stmt = stmt.where(UserPersona.total_trade_count >= 10)
        win_rate_expr = case(
            (UserPersona.total_trade_count > 0, 
             func.cast(UserPersona.win_count, Numeric) * 100.0 / func.cast(UserPersona.total_trade_count, Numeric)),
            else_=0
        )
        stmt = stmt.order_by(desc(win_rate_expr), desc(UserPersona.total_trade_count))

    elif ranking_type == "profit_factor":
        # Profit Factor: total_profit / total_loss
        pf_expr = case(
            (UserPersona.total_loss > 0, 
             UserPersona.total_profit / UserPersona.total_loss),
            else_=UserPersona.total_profit # If loss is 0, sort by profit
        )
        stmt = stmt.order_by(desc(pf_expr))

    elif ranking_type == "market_ratio":
        # Market Order Ratio: (market_order_count / total_trade_count) * 100
        stmt = stmt.where(UserPersona.total_trade_count > 0)
        mr_expr = case(
            (UserPersona.total_trade_count > 0, 
             func.cast(UserPersona.market_order_count, Numeric) * 100.0 / func.cast(UserPersona.total_trade_count, Numeric)),
            else_=0
        )
        stmt = stmt.order_by(desc(mr_expr))
    
    else:
        return []
    
    # DB-level Limit
    stmt = stmt.limit(limit)
        
    result = await db.execute(stmt)
    rows = result.all()
    
    rankings = []
    
    for i, (persona, user) in enumerate(rows):
        val = 0
        extra = None

        if ranking_type == "pnl": val = float(persona.total_realized_pnl)
        elif ranking_type == "loss": val = float(persona.total_loss)
        elif ranking_type == "volume": val = float(persona.total_trade_count)
        elif ranking_type == "fees": val = float(persona.total_fees_paid)
        elif ranking_type == "night": val = float(persona.night_trade_count)
        
        elif ranking_type == "win_rate":
            val = float(persona.win_count) / float(persona.total_trade_count) * 100 if persona.total_trade_count else 0
            val = round(val, 2)
            extra = {"trade_count": persona.total_trade_count}
            
        elif ranking_type == "profit_factor":
            loss = float(persona.total_loss)
            profit = float(persona.total_profit)
            if loss == 0:
                val = profit
            else:
                val = profit / loss
            val = round(val, 2)
            extra = {"profit": profit, "loss": loss}
            
        elif ranking_type == "market_ratio":
            val = float(persona.market_order_count) / float(persona.total_trade_count) * 100 if persona.total_trade_count else 0
            val = round(val, 2)
            extra = {"trade_count": persona.total_trade_count}

        rankings.append(RankingEntry(rank=i+1, nickname=user.nickname, value=val, extra_info=extra))
            
    return rankings
