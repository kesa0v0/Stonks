# backend/services/trade_service.py
import json
import redis.asyncio as async_redis
import uuid
import logging
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.models import User, Wallet, Portfolio, Order, Ticker
from backend.core.enums import OrderStatus, OrderSide, OrderType
from backend.core.config import settings

# 로깅 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

async def get_current_price(redis_client: async_redis.Redis, ticker_id: str) -> Decimal:
    """Redis에서 현재가 조회 (비동기)"""
    try:
        data = await redis_client.get(f"price:{ticker_id}")
        if not data:
            return None
        price_data = json.loads(data)
        return Decimal(str(price_data['price']))
    except Exception as e:
        logger.error(f"Failed to fetch price for {ticker_id}: {e}")
        return None

async def get_trading_fee_rate(redis_client: async_redis.Redis) -> Decimal:
    """거래 수수료율 조회 (비동기, 기본값 0.1%)"""
    try:
        rate = await redis_client.get("config:trading_fee_rate")
        if rate:
            if isinstance(rate, bytes):
                rate = rate.decode()
            return Decimal(str(rate))
        return Decimal("0.001")
    except Exception as e:
        logger.error(f"Failed to fetch fee rate: {e}")
        return Decimal("0.001")

async def execute_trade(db: AsyncSession, redis_client: async_redis.Redis, user_id: str, order_id: str, ticker_id: str, side: str, quantity: float):
    """
    주문 실행 및 체결 로직 (Atomic Transaction)
    공매도(Short Selling) 및 스위칭 매매 지원
    """
    quantity = Decimal(str(quantity))
    
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

    # 1. 현재가 및 수수료율 조회
    current_price = await get_current_price(redis_client, ticker_id)
    if current_price is None:
        logger.error(f"Price not found for {ticker_id}")
        return False
        
    fee_rate = await get_trading_fee_rate(redis_client)

    try:
        # 2. 유저 및 지갑 조회 (Pessimistic Lock 적용)
        # with_for_update()를 사용하여 트랜잭션 종료 시까지 Row Lock을 걺
        wallet_stmt = select(Wallet).where(Wallet.user_id == user_uuid).with_for_update()
        result = await db.execute(wallet_stmt)
        wallet = result.scalars().first()

        if not wallet:
            logger.error(f"Wallet not found for user {user_id}. Trade failed.")
            return False

        # 3. 주문 조회 또는 생성
        order_stmt = select(Order).where(Order.id == order_uuid)
        result = await db.execute(order_stmt)
        order = result.scalars().first()

        if not order:
            # Market 주문: DB에 없으므로 새로 생성
            order = Order(
                id=order_uuid,
                user_id=user_uuid,
                ticker_id=ticker_id,
                side=trade_side,
                quantity=quantity,
                price=current_price,
                type=OrderType.MARKET,
                status=OrderStatus.PENDING,
                unfilled_quantity=quantity
            )
            db.add(order)
        else:
            # Limit 주문
            order.price = current_price

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

        # 5. 매매 로직 (공매도/스위칭 포함)
        trade_amount = current_price * quantity
        fee = trade_amount * fee_rate
        
        current_qty = portfolio.quantity
        
        # [매수 (BUY)]
        if trade_side == OrderSide.BUY:
            total_cost = trade_amount + fee # 수수료 포함 비용
            
            # 지갑에서 돈 차감 (수수료 포함)
            if wallet.balance < total_cost:
                order.status = OrderStatus.FAILED
                order.fail_reason = f"매수 잔액이 부족합니다. (필요: {total_cost}, 보유: {wallet.balance})"
                await db.commit()
                logger.warning(f"Trade failed: Insufficient balance for user {user_id}")
                return False
            
            wallet.balance -= total_cost
            
            # A. 롱 -> 롱 (불타기/물타기)
            if current_qty >= 0:
                prev_total_val = current_qty * portfolio.average_price
                # 평단가에 수수료 녹임 (취득원가 상승)
                new_total_val = prev_total_val + total_cost 
                new_qty = current_qty + quantity
                
                # 수량이 0이면 평단가를 현재가로 (첫 진입)
                # 수량이 있으면 가중평균
                if new_qty > 0:
                    portfolio.average_price = new_total_val / new_qty
                    
                portfolio.quantity = new_qty
                
            # B. 숏 -> ? (상환 or 스위칭)
            else:
                remaining_qty = current_qty + quantity
                
                if remaining_qty <= 0:
                    # B-1. 숏 -> 숏/0 (상환)
                    # 상환 시 평단가는 변하지 않음 (FIFO/LIFO 등 복잡한 로직 대신 단순 차감)
                    portfolio.quantity = remaining_qty
                else:
                    # B-2. 숏 -> 롱 (스위칭)
                    portfolio.quantity = remaining_qty
                    portfolio.average_price = current_price

        # [매도 (SELL)]
        elif trade_side == OrderSide.SELL:
            net_income = trade_amount - fee # 수수료 차감 후 입금액
            
            # 지갑에 돈 입금
            wallet.balance += net_income
            
            # A. 롱 -> ? (청산 or 스위칭)
            if current_qty > 0:
                remaining_qty = current_qty - quantity
                
                if remaining_qty >= 0:
                    # A-1. 롱 -> 롱/0 (청산)
                    portfolio.quantity = remaining_qty
                else:
                    # A-2. 롱 -> 숏 (스위칭)
                    portfolio.quantity = remaining_qty
                    portfolio.average_price = current_price
            
            # B. 숏 -> 숏 (추가 공매도)
            else:
                # 숏 물타기
                prev_total_val = abs(current_qty) * portfolio.average_price
                # 평단가에 수수료 녹임 (수취 금액이 줄었으니 평단가가 낮아져야 함 -> 불리해짐)
                new_total_val = prev_total_val + net_income
                new_qty_abs = abs(current_qty - quantity)
                
                if new_qty_abs > 0:
                    portfolio.average_price = new_total_val / new_qty_abs
                
                portfolio.quantity -= quantity

        # 6. 마무리 (0 근처 삭제)
        if abs(portfolio.quantity) <= Decimal("1e-8"):
             await db.delete(portfolio)
        
        # 최종 커밋
        order.status = OrderStatus.FILLED
        order.unfilled_quantity = 0
        order.filled_at = func.now()
        await db.commit()
        
        logger.info(f"Trade Executed: {side} {quantity} {ticker_id} @ {current_price} (Fee: {fee}) for user {user_id}")
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
