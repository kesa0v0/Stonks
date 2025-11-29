from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from decimal import Decimal
import pytz

from backend.models import UserPersona
from backend.core.enums import OrderType

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
