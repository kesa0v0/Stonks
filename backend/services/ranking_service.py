from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime
from decimal import Decimal
import pytz
from typing import List

from backend.models import UserPersona, User
from backend.core.enums import OrderType
from backend.schemas.ranking import RankingEntry, HallOfFameResponse

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
    stmt = select(UserPersona).where(UserPersona.user_id == user_id)
    result = await db.execute(stmt)
    persona = result.scalars().first()
    
    if not persona:
        # 명시적으로 초기값 할당하여 NoneType 에러 방지
        persona = UserPersona(
            user_id=user_id,
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
    
    # 2. 시간대 체크 (한국 시간 기준 새벽 2시~5시 = 미국 주식 좀비)
    # 현재 시간을 KST로 변환
    now_utc = datetime.now(pytz.utc)
    kst = pytz.timezone('Asia/Seoul')
    now_kst = now_utc.astimezone(kst)
    
    if 2 <= now_kst.hour < 5:
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

async def get_rankings_data(
    db: AsyncSession,
    ranking_type: str,
    limit: int
) -> List[RankingEntry]:
    """
    랭킹 조회 로직
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
        # Router에서 유효성 검사를 했거나, 여기서 에러 발생 (하지만 보통 router에서 validation 함)
        # 여기서는 빈 리스트 반환하거나 에러 발생
        return []
    
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
