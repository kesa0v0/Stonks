# backend/services/trade_service.py
import json
import redis
import uuid
import logging
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
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

# Redis 연결 (시세 조회용, 동기식 사용)
r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)

def get_current_price(ticker_id: str) -> Decimal:
    """Redis에서 현재가 조회"""
    try:
        data = r.get(f"price:{ticker_id}")
        if not data:
            return None
        price_data = json.loads(data)
        return Decimal(str(price_data['price']))
    except Exception as e:
        logger.error(f"Failed to fetch price for {ticker_id}: {e}")
        return None

def execute_trade(db: Session, user_id: str, order_id: str, ticker_id: str, side: str, quantity: float):
    """
    주문 실행 및 체결 로직 (Atomic Transaction)
    공매도(Short Selling) 및 스위칭 매매 지원
    """
    quantity = Decimal(str(quantity))

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

    # 1. 현재가 조회
    current_price = get_current_price(ticker_id)
    if current_price is None:
        logger.error(f"Price not found for {ticker_id}")
        return False

    # 2. 유저 및 지갑 조회 (Pessimistic Lock 적용)
    # with_for_update()를 사용하여 트랜잭션 종료 시까지 Row Lock을 걺
    wallet = db.query(Wallet).filter(Wallet.user_id == user_uuid).with_for_update().first()
    if not wallet:
        logger.error(f"Wallet not found for user {user_id}. Trade failed.")
        # 지갑이 없으면 실패 처리 (자동 생성 로직 삭제함)
        return False

    # 3. 주문 조회 또는 생성
    order = db.query(Order).filter(Order.id == order_uuid).first()

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
    # 없으면 생성해야 하므로, 일단 조회 시도
    portfolio = db.query(Portfolio).filter(
        Portfolio.user_id == user_uuid, 
        Portfolio.ticker_id == ticker_id
    ).with_for_update().first()
    
    if not portfolio:
        portfolio = Portfolio(user_id=user_uuid, ticker_id=ticker_id, quantity=0, average_price=0)
        db.add(portfolio)

    # 5. 매매 로직 (공매도/스위칭 포함)
    try:
        trade_amount = current_price * quantity
        current_qty = portfolio.quantity
        
        # [매수 (BUY)]
        if trade_side == OrderSide.BUY:
            # 지갑에서 돈 차감
            if wallet.balance < trade_amount:
                order.status = OrderStatus.FAILED
                order.fail_reason = f"Insufficient balance (Req: {trade_amount}, Bal: {wallet.balance})"
                db.commit()
                logger.warning(f"Trade failed: Insufficient balance for user {user_id}")
                return False
            
            wallet.balance -= trade_amount
            
            # A. 롱 -> 롱 (불타기/물타기)
            if current_qty >= 0:
                prev_total_val = current_qty * portfolio.average_price
                new_total_val = prev_total_val + trade_amount
                new_qty = current_qty + quantity
                
                # 수량이 0이면 평단가를 현재가로 (첫 진입)
                # 수량이 있으면 가중평균
                if new_qty > 0:
                    portfolio.average_price = new_total_val / new_qty
                else:
                    portfolio.average_price = current_price # 0일때 의미 없지만 초기화
                    
                portfolio.quantity = new_qty
                
            # B. 숏 -> ? (상환 or 스위칭)
            else:
                remaining_qty = current_qty + quantity
                
                if remaining_qty <= 0:
                    # B-1. 숏 -> 숏/0 (상환)
                    portfolio.quantity = remaining_qty
                else:
                    # B-2. 숏 -> 롱 (스위칭)
                    portfolio.quantity = remaining_qty
                    portfolio.average_price = current_price

        # [매도 (SELL)]
        elif trade_side == OrderSide.SELL:
            # 지갑에 돈 입금
            wallet.balance += trade_amount
            
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
                new_total_val = prev_total_val + trade_amount
                new_qty_abs = abs(current_qty - quantity)
                
                if new_qty_abs > 0:
                    portfolio.average_price = new_total_val / new_qty_abs
                
                portfolio.quantity -= quantity

        # 6. 마무리 (0 근처 삭제)
        if abs(portfolio.quantity) <= Decimal("1e-8"):
             db.delete(portfolio)
        
        # 최종 커밋
        order.status = OrderStatus.FILLED
        order.unfilled_quantity = 0
        order.filled_at = func.now()
        db.commit()
        
        logger.info(f"Trade Executed: {side} {quantity} {ticker_id} @ {current_price} for user {user_id}")
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Trade Execution Logic Error: {e}", exc_info=True)
        order.status = OrderStatus.FAILED
        order.fail_reason = str(e)
        db.commit()
        return False