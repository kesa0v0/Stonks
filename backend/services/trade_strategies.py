from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.core.enums import OrderSide, OrderStatus
from backend.core.constants import (
    WALLET_REASON_TRADE_BUY,
    WALLET_REASON_TRADE_SELL,
)
from backend.services.common.wallet import add_balance, sub_balance
from backend.services.dividend_service import process_dividend
from backend.models import User, Wallet, Portfolio, Order


@dataclass
class TradeContext:
    db: AsyncSession
    wallet: Wallet
    portfolio: Portfolio
    order: Order
    current_price: Decimal
    quantity: Decimal
    trade_amount: Decimal
    fee: Decimal
    fee_rate: Decimal
    user_id: UUID
    ticker_id: str


class TradeStrategy:
    async def execute(self, ctx: TradeContext) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class BuyStrategy(TradeStrategy):
    async def execute(self, ctx: TradeContext) -> bool:
        total_cost = ctx.trade_amount + ctx.fee

        # 잔액 부족 시 실패 처리
        if ctx.wallet.balance < total_cost:
            ctx.order.status = OrderStatus.FAILED
            ctx.order.fail_reason = (
                f"매수 잔액이 부족합니다. (필요: {total_cost}, 보유: {ctx.wallet.balance})"
            )
            await ctx.db.commit()
            return False

        sub_balance(ctx.wallet, total_cost, WALLET_REASON_TRADE_BUY)

        current_qty = ctx.portfolio.quantity

        # 숏 상환 시 PnL 계산
        if current_qty < 0:
            closing_qty = min(abs(current_qty), ctx.quantity)
            allocated_fee = ctx.fee * (closing_qty / ctx.quantity)
            pnl = (ctx.portfolio.average_price - ctx.current_price) * closing_qty - allocated_fee
            ctx.order.realized_pnl = pnl

        if current_qty >= 0:
            prev_total_val = current_qty * ctx.portfolio.average_price
            new_total_val = prev_total_val + total_cost
            new_qty = current_qty + ctx.quantity
            if new_qty > 0:
                ctx.portfolio.average_price = new_total_val / new_qty
            ctx.portfolio.quantity = new_qty
        else:
            remaining_qty = current_qty + ctx.quantity
            if remaining_qty <= 0:
                ctx.portfolio.quantity = remaining_qty
            else:
                ctx.portfolio.quantity = remaining_qty
                ctx.portfolio.average_price = ctx.current_price

        return True


class SellStrategy(TradeStrategy):
    async def execute(self, ctx: TradeContext) -> bool:
        current_qty = ctx.portfolio.quantity
        net_income = ctx.trade_amount - ctx.fee
        
        # PnL 및 배당금 계산을 먼저 수행 (원천징수 적용)
        pnl = Decimal(0)
        closing_qty = Decimal(0)
        
        if current_qty > 0:
            closing_qty = min(current_qty, ctx.quantity)
            allocated_fee = ctx.fee * (closing_qty / ctx.quantity)
            pnl = (ctx.current_price - ctx.portfolio.average_price) * closing_qty - allocated_fee
            ctx.order.realized_pnl = pnl

        # 배당금 원천징수 로직
        dividend_withheld = Decimal(0)
        if pnl > 0:
            user_stmt = select(User).where(User.id == ctx.user_id)
            user_res = await ctx.db.execute(user_stmt)
            current_user = user_res.scalars().first()
            if current_user and current_user.dividend_rate > 0:
                # deduct_source=False: 지갑에서 차감하지 않고, 우리가 직접 net_income에서 제함
                dividend_withheld = await process_dividend(ctx.db, current_user, pnl, deduct_source=False)
        
        # 최종 입금액 결정 (수익금 - 배당금)
        final_income = net_income - dividend_withheld
        add_balance(ctx.wallet, final_income, WALLET_REASON_TRADE_SELL)

        # 롱 -> 롱/0 or 스위칭 -> 숏
        if current_qty > 0:
            remaining_qty = current_qty - ctx.quantity
            if remaining_qty >= 0:
                ctx.portfolio.quantity = remaining_qty
            else:
                ctx.portfolio.quantity = remaining_qty
                ctx.portfolio.average_price = ctx.current_price
        else:
            # 이미 숏이면 물타기 로직으로 위임 (입금은 숏 전략에서 처리)
            # 주의: 위에서 이미 add_balance를 했으므로 ShortSellStrategy에서는 add_balance를 중복하면 안됨.
            # 하지만 ShortSellStrategy.execute()는 자체적으로 add_balance를 수행함.
            # 따라서 여기서는 ShortSellStrategy를 직접 호출하지 말고 로직을 구현하거나, 
            # ShortSellStrategy가 add_balance를 하지 않도록 수정해야 함.
            
            # 현재 코드 구조상 ShortSellStrategy.execute()는 무조건 add_balance를 함.
            # 따라서 여기서는 return await ShortSellStrategy().execute(ctx)를 호출하면 중복 입금됨.
            
            # 해결책: ShortSellStrategy 로직을 여기에 인라인으로 구현 (중복 입금 방지)
            
            # --- Short Logic Inline ---
            # (이미 위에서 add_balance 했음)
            
            # current_qty는 음수 (숏 포지션)
            prev_total_val = abs(current_qty) * ctx.portfolio.average_price
            new_total_val = prev_total_val + net_income # 숏 추가 시 확보한 현금이 가치 희석? (기존 로직 따름)
            # ShortSellStrategy 로직:
            # new_total_val = prev_total_val + net_income
            # new_qty_abs = abs(current_qty - ctx.quantity) -> 이건 current_qty가 숏일때 quantity(매도)를 더하는 상황?
            # 잠깐, ctx.quantity는 매도 수량.
            # 숏 포지션에서 매도(Sell)는 "추가 공매도"임.
            # current_qty = -10. Sell 5. -> New Qty = -15.
            
            # ShortSellStrategy 로직 복사:
            # current_qty = ctx.portfolio.quantity
            # prev_total_val = abs(current_qty) * ctx.portfolio.average_price
            # new_total_val = prev_total_val + net_income
            # new_qty_abs = abs(current_qty - ctx.quantity) -> 여기서 ctx.quantity는 양수.
            # current_qty - ctx.quantity -> -10 - 5 = -15. abs = 15. Correct.
            
            new_qty_abs = abs(current_qty - ctx.quantity)
            if new_qty_abs > 0:
                 # 평단가 갱신: (기존총액 + 신규확보금액) / 총수량
                 # 공매도는 판 금액만큼 현금을 확보하므로, 확보한 현금이 담보/평가액에 반영됨.
                 ctx.portfolio.average_price = new_total_val / new_qty_abs

            ctx.portfolio.quantity -= ctx.quantity
            # --- End Short Logic ---

        return True


class ShortSellStrategy(TradeStrategy):
    async def execute(self, ctx: TradeContext) -> bool:
        net_income = ctx.trade_amount - ctx.fee
        add_balance(ctx.wallet, net_income, WALLET_REASON_TRADE_SELL)

        current_qty = ctx.portfolio.quantity
        prev_total_val = abs(current_qty) * ctx.portfolio.average_price
        new_total_val = prev_total_val + net_income
        new_qty_abs = abs(current_qty - ctx.quantity)

        if new_qty_abs > 0:
            ctx.portfolio.average_price = new_total_val / new_qty_abs

        ctx.portfolio.quantity -= ctx.quantity
        return True
