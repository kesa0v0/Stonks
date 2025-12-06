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

        # 롱 청산 시 PnL/배당 처리
        if current_qty > 0:
            add_balance(ctx.wallet, net_income, WALLET_REASON_TRADE_SELL)
            closing_qty = min(current_qty, ctx.quantity)
            allocated_fee = ctx.fee * (closing_qty / ctx.quantity)
            pnl = (ctx.current_price - ctx.portfolio.average_price) * closing_qty - allocated_fee
            ctx.order.realized_pnl = pnl

            if pnl > 0:
                user_stmt = select(User).where(User.id == ctx.user_id)
                user_res = await ctx.db.execute(user_stmt)
                current_user = user_res.scalars().first()
                if current_user and current_user.dividend_rate > 0:
                    await process_dividend(ctx.db, current_user, pnl)

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
            return await ShortSellStrategy().execute(ctx)

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
