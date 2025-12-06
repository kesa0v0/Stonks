# backend/services/trade_service.py
import json
import redis.asyncio as async_redis
import uuid
import logging
import time
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from backend.models import User, Wallet, Portfolio, Order, Ticker, MarketType
from backend.core.enums import OrderStatus, OrderSide, OrderType
from backend.core.config import settings
from backend.core.event_hook import publish_event
from backend.services.ranking_service import update_user_persona
from backend.services.common.price import get_current_price
from backend.services.common.config import get_trading_fee_rate
from backend.services.common.wallet import add_balance, sub_balance
from backend.core.constants import (
    WALLET_REASON_TRADE_BUY,
    WALLET_REASON_TRADE_SELL,
)
from backend.services.trade_strategies import (
    TradeContext,
    BuyStrategy,
    SellStrategy,
    ShortSellStrategy,
)

# 로깅 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

async def execute_trade(db: AsyncSession, redis_client: async_redis.Redis, user_id: str, order_id: str, ticker_id: str, side: str, quantity: float):
    """
    주문 실행 및 체결 로직 (Atomic Transaction)
    공매도(Short Selling) 및 스위칭 매매 지원
    """
    original_requested_quantity = Decimal(str(quantity)) # Capture the initial requested quantity from the argument
    quantity = original_requested_quantity # `quantity` variable will represent the amount to be executed in this call
    
    if quantity <= 0:
        logger.warning(f"Trade quantity must be positive: {quantity}")
        return False

    # UUID 유효성 검사
    try:
        user_uuid = uuid.UUID(user_id)
        order_uuid = uuid.UUID(order_id)
    except ValueError:
        logger.error(f"Invalid UUID format: user={user_id}, order={order_id}")
        return False
    
    # 거래 방향 유효성 검사
    try:
        trade_side = OrderSide(side) 
    except ValueError:
        logger.error(f"Invalid Side: {side}")
        return False

    # Ticker 조회 및 MarketType 확인
    ticker_stmt = select(Ticker).where(Ticker.id == ticker_id)
    ticker = (await db.execute(ticker_stmt)).scalars().first()
    
    if not ticker:
        logger.error(f"Ticker not found: {ticker_id}")
        return False

    # [Human ETF 특수 처리]
    # P2P 매칭이 필요한 Human ETF는 즉시 체결(Infinite Liquidity)하지 않고, 주문장에 등록만 함.
    if ticker.market_type == MarketType.HUMAN:
        order_stmt = select(Order).where(Order.id == order_uuid)
        result = await db.execute(order_stmt)
        order = result.scalars().first()

        if not order:
            # 신규 주문 (API에서 요청된 Market Order 등) -> OrderBook 등록
            order = Order(
                id=order_uuid,
                user_id=user_uuid,
                ticker_id=ticker_id,
                side=trade_side,
                quantity=quantity,
                type=OrderType.MARKET, # 명시되지 않았으면 Market으로 가정
                status=OrderStatus.PENDING,
                unfilled_quantity=quantity
            )
            db.add(order)
            logger.info(f"Human ETF Order Queued: {side} {quantity} {ticker_id} (User {user_id})")
        else:
            # 기존 주문 (Stop Loss 트리거 등) -> Active 상태로 변경하여 매처가 잡을 수 있게 함
            # Stop 계열 주문이 트리거되어 execute_trade가 호출된 경우 -> MARKET 주문으로 전환
            if order.type in [OrderType.STOP_LOSS, OrderType.STOP_LIMIT, OrderType.TAKE_PROFIT, OrderType.TRAILING_STOP]:
                order.type = OrderType.MARKET
                # Triggered Log
                logger.info(f"Human ETF Stop Order Triggered -> Converted to MARKET: {order.id}")
            
            # 상태는 PENDING 유지 (매처가 처리)
            order.status = OrderStatus.PENDING

        await db.commit()
        
        # [Event Hook] Human ETF 주문 접수/업데이트 알림 (Frontend 반영용)
        event = {
            "type": "order_accepted", 
            "user_id": str(user_uuid),
            "order_id": str(order_uuid),
            "ticker_id": ticker_id,
            "side": str(trade_side),
            "quantity": str(quantity),
            "price": str(order.price) if order.price else "0",
            "status": str(OrderStatus.PENDING)
        }
        await publish_event(redis_client, event, channel="trade_events")

        return True

    # 1. 가격 결정 (Slippage 적용)
    # 호가창(Orderbook)을 조회하여 주문 수량만큼 갉아먹었을 때의 평균 단가(VWAP)를 계산합니다.
    # 호가창이 비어있거나 유동성이 부족하면 현재가(Last Price)로 Fallback 합니다.
    from backend.services.market_service import get_orderbook_data
    
    execution_price = None
    filled_qty_from_ob = Decimal(0) # Quantity actually filled from the order book
    
    try:
        orderbook = await get_orderbook_data(db, ticker_id, redis_client)
        liquidity = orderbook.asks if trade_side == OrderSide.BUY else orderbook.bids
        
        needed_qty_from_order = quantity # The total quantity the user wants to buy/sell
        total_cost_from_ob = Decimal(0)
        
        for entry in liquidity:
            if needed_qty_from_order <= 0:
                break
            
            available_in_level = entry.quantity
            matched_in_level = min(needed_qty_from_order, available_in_level)
            
            total_cost_from_ob += matched_in_level * entry.price
            filled_qty_from_ob += matched_in_level
            needed_qty_from_order -= matched_in_level
            
        if filled_qty_from_ob > 0: # If anything was filled from the order book
            execution_price = total_cost_from_ob / filled_qty_from_ob
            logger.info(f"Slippage Applied for {ticker_id}: {filled_qty_from_ob} units @ {execution_price} from Orderbook.")
        
        # If there's still a remaining quantity after checking order book, it means insufficient liquidity.
        # The order can either be partially filled or rejected if nothing was filled.
        if needed_qty_from_order > 0:
            logger.warning(f"Insufficient liquidity for {ticker_id}. Requested: {quantity}, Filled from OB: {filled_qty_from_ob}. Remaining: {needed_qty_from_order}.")
            
            if filled_qty_from_ob == 0:
                 # If absolutely nothing could be filled from orderbook, reject the order.
                 logger.error(f"Market order {order_id} for {ticker_id} failed: No liquidity in order book.")
                 return False
            
            # Adjust the 'quantity' variable for the rest of the trade logic to only what was filled from the order book.
            # This makes it a partial fill.
            quantity = filled_qty_from_ob
            
            # The order's `unfilled_quantity` will be updated later.
            # We don't need to explicitly update `order.quantity` here, as the original order object `order`
            # might not be created yet if it's a new market order (order is created later if not found).
            # The `quantity` parameter passed to strategy.execute will be the filled amount.

    except Exception as e:
        logger.error(f"Error calculating slippage for {ticker_id}: {e}. Market order {order_id} for {ticker_id} failed due to order book access error.", exc_info=True)
        return False # Fail if order book access fails.

    # At this point, execution_price must be set if filled_qty_from_ob > 0.
    # If filled_qty_from_ob was 0, the function would have returned False already.
    if execution_price is None:
        logger.error(f"Market order {order_id} for {ticker_id} failed: No execution price could be determined after order book check.")
        return False
    
    current_price = execution_price
    
    if current_price is None:
        logger.error(f"Price not found for {ticker_id} after order book processing. Market order {order_id} failed.")
        return False
        
    fee_rate = await get_trading_fee_rate(redis_client)

    try:
        # 2. 유저 및 지갑 조회 (Pessimistic Lock 적용)
        # with_for_update()를 사용하여 트랜잭션 종료 시까지 Row Lock을 걺
        wallet_stmt = select(Wallet).where(Wallet.user_id == user_uuid).with_for_update()
        result = await db.execute(wallet_stmt)
        wallet = result.scalars().first()

        if not wallet:
            logger.error(f"Wallet not found for user {user_id}. Trade failed for order {order_id}.")
            return False

        # 3. 주문 조회 또는 생성
        order_stmt = select(Order).where(Order.id == order_uuid)
        result = await db.execute(order_stmt)
        order = result.scalars().first()

        if not order:
            # Market 주문: DB에 없으므로 새로 생성
            # `quantity` here is the `filled_qty_from_ob` (the amount actually executed in this call)
            # `original_requested_quantity` is the total quantity the user initially requested.
            order = Order(
                id=order_uuid,
                user_id=user_uuid,
                ticker_id=ticker_id,
                side=trade_side,
                quantity=original_requested_quantity, # Total requested quantity by user
                price=current_price, # This is the VWAP from OB for the filled amount
                type=OrderType.MARKET,
                status=OrderStatus.PENDING, # Initially pending, even if partially filled.
                unfilled_quantity=original_requested_quantity - quantity # Remaining to be filled (0 if fully filled from OB)
            )
            db.add(order)
        else:
            # Existing order (e.g., a triggered LIMIT/STOP order that became MARKET)
            order.price = current_price # Set execution price
            # Reduce unfilled quantity by the amount actually filled from the order book (`quantity` variable)
            order.unfilled_quantity -= quantity 

        # 4. 포트폴리오 조회 (Pessimistic Lock 적용)
        portfolio_stmt = select(Portfolio).where(
            Portfolio.user_id == user_uuid, 
            Portfolio.ticker_id == ticker_id
        ).with_for_update()
        result = await db.execute(portfolio_stmt)
        portfolio = result.scalars().first()
        
        if not portfolio:
            portfolio = Portfolio(user_id=user_uuid, ticker_id=ticker_id, quantity=0, average_price=0)
            db.add(portfolio)

        # 5. 매매 로직 (Strategy Pattern)
        trade_amount = current_price * quantity # Use the filled quantity for trade amount calculation
        fee = trade_amount * fee_rate

        ctx = TradeContext(
            db=db,
            wallet=wallet,
            portfolio=portfolio,
            order=order,
            current_price=current_price,
            quantity=quantity, # Pass the filled quantity to the strategy
            trade_amount=trade_amount,
            fee=fee,
            fee_rate=fee_rate,
            user_id=user_uuid,
            ticker_id=ticker_id,
        )

        if trade_side == OrderSide.BUY:
            strategy = BuyStrategy()
        elif trade_side == OrderSide.SELL and portfolio.quantity > 0:
            strategy = SellStrategy()
        else:
            strategy = ShortSellStrategy()

        strategy_success = await strategy.execute(ctx)
        if not strategy_success:
            logger.warning(f"Trade failed during strategy execution for user {user_id}. Order {order_id}.")
            return False

        # 6. 마무리 (0 근처 삭제)
        if abs(portfolio.quantity) <= Decimal("1e-8"):
             await db.delete(portfolio)
        
        # [RANKING] 사용자 페르소나 업데이트
        await update_user_persona(
            db=db,
            user_id=user_uuid,
            order_type=order.type,
            pnl=order.realized_pnl,
            fee=fee
        )

        # 최종 커밋
        # Update order status based on remaining unfilled quantity
        if order.unfilled_quantity <= 0:
            order.status = OrderStatus.FILLED
            order.unfilled_quantity = 0 # Ensure it's exactly 0
        else:
            order.status = OrderStatus.PENDING # If partially filled, remain PENDING
        order.filled_at = func.now() # Update filled_at on successful execution (partial or full)
        await db.commit()
        
        logger.info(f"Trade Executed: {side} {quantity} {ticker_id} @ {current_price} (Fee: {fee}) for user {user_id}. Order {order_id}. Remaining unfilled: {order.unfilled_quantity}")

        # Post-Trade Event Hook: 거래 이벤트 발행
        event = {
            "type": "trade_executed",
            "user_id": str(user_id),
            "order_id": str(order_id),
            "ticker_id": str(ticker_id),
            "side": str(side),
            "quantity": str(quantity), # This is the executed quantity (filled from OB)
            "price": str(current_price),
            "fee": str(fee),
            "realized_pnl": str(order.realized_pnl) if hasattr(order, "realized_pnl") and order.realized_pnl is not None else None,
            "status": str(order.status)
        }
        await publish_event(redis_client, event, channel="trade_events")
        return True

    except Exception as e:
        await db.rollback()
        logger.error(f"Trade Execution Logic Error: {e}", exc_info=True)
        try:
            # 실패 상태 업데이트를 위한 별도 트랜잭션 (만약 order가 세션에 있다면)
             if order:
                order.status = OrderStatus.FAILED
                order.fail_reason = f"시스템 오류: {str(e)}"
                await db.commit()
        except:
            pass # 실패 업데이트 중 에러는 무시
        return False

async def execute_p2p_trade(
    db: AsyncSession,
    redis_client: async_redis.Redis,
    buy_order_id: UUID,
    sell_order_id: UUID,
    match_price: Decimal,
    match_quantity: Decimal
) -> bool:
    """
    P2P 주문 매칭 및 체결 (Human ETF용)
    두 주문(Buy/Sell)을 받아 atomic하게 체결 처리.
    """
    match_quantity = Decimal(str(match_quantity))
    match_price = Decimal(str(match_price))
    
    if match_quantity <= 0:
        return False

    # 수수료율 조회
    fee_rate = await get_trading_fee_rate(redis_client)

    try:
        # 1. 주문 조회 및 Lock
        # 순서대로 Lock하여 Deadlock 방지 (ID 기준 정렬 등)은 여기선 생략하고, 
        # with_for_update()로 가져옴.
        # DB Deadlock 가능성이 있으나, Matcher가 단일 스레드/프로세스로 동작한다면 충돌 없음.
        
        # Buy Order
        buy_order_stmt = select(Order).where(Order.id == buy_order_id).with_for_update()
        buy_order = (await db.execute(buy_order_stmt)).scalars().first()
        
        # Sell Order
        sell_order_stmt = select(Order).where(Order.id == sell_order_id).with_for_update()
        sell_order = (await db.execute(sell_order_stmt)).scalars().first()

        if not buy_order or not sell_order:
            logger.error("P2P Match failed: Order not found")
            return False
            
        if buy_order.status != OrderStatus.PENDING or sell_order.status != OrderStatus.PENDING:
             logger.error("P2P Match failed: Order not PENDING")
             return False

        ticker_id = buy_order.ticker_id
        
        # 2. 유저 및 지갑 조회 (Pessimistic Lock)
        buyer_wallet_stmt = select(Wallet).where(Wallet.user_id == buy_order.user_id).with_for_update()
        buyer_wallet = (await db.execute(buyer_wallet_stmt)).scalars().first()
        
        seller_wallet_stmt = select(Wallet).where(Wallet.user_id == sell_order.user_id).with_for_update()
        seller_wallet = (await db.execute(seller_wallet_stmt)).scalars().first()

        if not buyer_wallet or not seller_wallet:
            logger.error("P2P Match failed: Wallet not found")
            return False

        # 3. 포트폴리오 조회 (Pessimistic Lock)
        buyer_pf_stmt = select(Portfolio).where(
            Portfolio.user_id == buy_order.user_id, 
            Portfolio.ticker_id == ticker_id
        ).with_for_update()
        buyer_pf = (await db.execute(buyer_pf_stmt)).scalars().first()
        
        if not buyer_pf:
            buyer_pf = Portfolio(user_id=buy_order.user_id, ticker_id=ticker_id, quantity=0, average_price=0)
            db.add(buyer_pf)
            
        seller_pf_stmt = select(Portfolio).where(
            Portfolio.user_id == sell_order.user_id, 
            Portfolio.ticker_id == ticker_id
        ).with_for_update()
        seller_pf = (await db.execute(seller_pf_stmt)).scalars().first()
        
        if not seller_pf:
            seller_pf = Portfolio(user_id=sell_order.user_id, ticker_id=ticker_id, quantity=0, average_price=0)
            db.add(seller_pf)

        # 4. 정산 계산
        trade_amount = match_price * match_quantity
        fee = trade_amount * fee_rate
        
        buyer_cost = trade_amount + fee
        seller_income = trade_amount - fee
        
        # 5. 잔액 검사 (Buyer만)
        if buyer_wallet.balance < buyer_cost:
            # 매수자 잔액 부족 -> 매수 주문 취소/실패 처리? 
            # 여기서는 매칭 실패로 처리하고 로깅. 
            # (실제로는 부분 체결이나 주문 취소가 더 나을 수 있음)
            logger.warning(f"P2P Match failed: Insufficient balance for buyer {buy_order.user_id}")
            # buy_order.status = OrderStatus.FAILED
            # buy_order.fail_reason = "Insufficient balance during match"
            # await db.commit()
            return False

        # 6. 자산 이전 및 상태 업데이트
        
        # [BUYER SIDE]
        sub_balance(buyer_wallet, buyer_cost, WALLET_REASON_TRADE_BUY)
        
        # Buyer Portfolio Update
        b_curr_qty = buyer_pf.quantity
        
        # 숏 포지션 상환 (Closing Short)
        if b_curr_qty < 0:
            closing_qty = min(abs(b_curr_qty), match_quantity)
            allocated_fee = fee * (closing_qty / match_quantity)
            pnl = (buyer_pf.average_price - match_price) * closing_qty - allocated_fee
            
            # 기존 PnL에 누적 (한 주문이 여러번 체결될 수 있음)
            buy_order.realized_pnl = (buy_order.realized_pnl or 0) + pnl
        
        # 롱 포지션 증가 (불타기)
        if b_curr_qty >= 0:
            prev_total_val = b_curr_qty * buyer_pf.average_price
            new_total_val = prev_total_val + buyer_cost
            new_qty = b_curr_qty + match_quantity
            if new_qty > 0:
                buyer_pf.average_price = new_total_val / new_qty
            buyer_pf.quantity = new_qty
        else:
            # 숏 -> 롱/상환
            remaining_qty = b_curr_qty + match_quantity
            if remaining_qty <= 0:
                buyer_pf.quantity = remaining_qty
            else:
                buyer_pf.quantity = remaining_qty
                buyer_pf.average_price = match_price

        # [SELLER SIDE]
        add_balance(seller_wallet, seller_income, WALLET_REASON_TRADE_SELL)
        
        # Seller Portfolio Update
        s_curr_qty = seller_pf.quantity
        
        # 롱 포지션 청산 (Closing Long)
        if s_curr_qty > 0:
            closing_qty = min(s_curr_qty, match_quantity)
            allocated_fee = fee * (closing_qty / match_quantity)
            pnl = (match_price - seller_pf.average_price) * closing_qty - allocated_fee
            
            sell_order.realized_pnl = (sell_order.realized_pnl or 0) + pnl
            
            # **중요**: P2P 거래에서도 수익이 나면 User Persona 업데이트는 필요하지만,
            # Human ETF 자체의 배당(Dividend)은 발생하지 않음 (배당은 Underlying User의 수익에서 발생).
            
        # 롱 -> ? (청산/스위칭)
        if s_curr_qty > 0:
            remaining_qty = s_curr_qty - match_quantity
            if remaining_qty >= 0:
                seller_pf.quantity = remaining_qty
            else:
                seller_pf.quantity = remaining_qty
                seller_pf.average_price = match_price
        else:
            # 숏 -> 숏 (추가 공매도)
            prev_total_val = abs(s_curr_qty) * seller_pf.average_price
            new_total_val = prev_total_val + seller_income # 수취 금액만큼 가치 희석? (execute_trade 로직 따름)
            # execute_trade의 로직: "평단가에 수수료 녹임 (수취 금액이 줄었으니 평단가가 낮아져야 함 -> 불리해짐)"
            # 숏 평균단가 = (기존가치 + 신규확보현금) / 총수량 ??
            # execute_trade 로직 그대로:
            new_qty_abs = abs(s_curr_qty - match_quantity)
            if new_qty_abs > 0:
                 seller_pf.average_price = new_total_val / new_qty_abs
            seller_pf.quantity -= match_quantity

        # 7. 포트폴리오 정리 (0 근처 삭제)
        if abs(buyer_pf.quantity) <= Decimal("1e-8"): await db.delete(buyer_pf)
        if abs(seller_pf.quantity) <= Decimal("1e-8"): await db.delete(seller_pf)

        # 8. 주문 상태 업데이트
        buy_order.unfilled_quantity -= match_quantity
        if buy_order.unfilled_quantity <= 0:
            buy_order.status = OrderStatus.FILLED
            buy_order.filled_at = func.now()
        
        sell_order.unfilled_quantity -= match_quantity
        if sell_order.unfilled_quantity <= 0:
            sell_order.status = OrderStatus.FILLED
            sell_order.filled_at = func.now()
            
        # 체결가 기록 (가장 최근 체결가)
        buy_order.price = match_price
        sell_order.price = match_price

        await db.commit()
        
        logger.info(f"P2P Trade: {ticker_id} {match_quantity} @ {match_price} | Buyer {buy_order.user_id} | Seller {sell_order.user_id}")

        # 9. 가격 업데이트 (Redis) & 이벤트 발행
        price_data = {
            "ticker_id": ticker_id,
            "price": str(match_price),
            "timestamp": float(time.time())
        }
        # Redis에 현재가 저장 (다른 서비스/frontend 참조용)
        await redis_client.set(f"{constants.REDIS_PREFIX_PRICE}{ticker_id}", json.dumps(price_data))
        # Market Update PubSub (Limit Matcher가 반응할 수도 있음 - 하지만 Human ETF는 Limit Matcher가 안돔)
        await redis_client.publish("market_updates", json.dumps(price_data))
        
        # Trade Event (Buyer)
        await publish_event(redis_client, {
            "type": "trade_executed",
            "user_id": str(buy_order.user_id),
            "order_id": str(buy_order.id),
            "ticker_id": ticker_id,
            "side": "BUY",
            "quantity": str(match_quantity),
            "price": str(match_price),
            "fee": str(fee),
            "realized_pnl": str(buy_order.realized_pnl or 0),
            "status": str(buy_order.status)
        }, channel="trade_events")
        
        # Trade Event (Seller)
        await publish_event(redis_client, {
            "type": "trade_executed",
            "user_id": str(sell_order.user_id),
            "order_id": str(sell_order.id),
            "ticker_id": ticker_id,
            "side": "SELL",
            "quantity": str(match_quantity),
            "price": str(match_price),
            "fee": str(fee),
            "realized_pnl": str(sell_order.realized_pnl or 0),
            "status": str(sell_order.status)
        }, channel="trade_events")

        return True

    except Exception as e:
        await db.rollback()
        logger.error(f"P2P Trade Execution Error: {e}", exc_info=True)
        return False
