# backend/services/trade_service.py
import json
import redis
import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.models import User, Wallet, Portfolio, Order, OrderStatus, OrderSide, OrderType, Ticker
from backend.core.config import settings

# Redis 연결 (시세 조회용, 동기식 사용)
r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)

def get_current_price(ticker_id: str) -> Decimal:
    """Redis에서 현재가 조회"""
    data = r.get(f"price:{ticker_id}")
    if not data:
        return None
    price_data = json.loads(data)
    return Decimal(str(price_data['price']))

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
        print(f"❌ Invalid UUID format: user={user_id}, order={order_id}")
        return False
    
    # 거래 방향 유효성 검사
    try:
        trade_side = OrderSide(side) 
    except ValueError:
        print(f"❌ Invalid Side: {side}")
        return False

    # 1. 현재가 조회
    current_price = get_current_price(ticker_id)
    if current_price is None:
        print(f"❌ Price not found for {ticker_id}")
        return False

    # 2. 유저 및 지갑 조회
    wallet = db.query(Wallet).filter(Wallet.user_id == user_uuid).first()
    if not wallet:
        wallet = Wallet(user_id=user_uuid, balance=100000000) # 초기자금 1억
        db.add(wallet)
        db.commit()
        db.refresh(wallet)

    # 3. 주문 조회 또는 생성
    order = db.query(Order).filter(Order.id == order_uuid).first()

    if not order:
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
        order.price = current_price

    # 4. 포트폴리오 조회 (없으면 0으로 생성)
    portfolio = db.query(Portfolio).filter(
        Portfolio.user_id == user_uuid, 
        Portfolio.ticker_id == ticker_id
    ).first()
    
    if not portfolio:
        portfolio = Portfolio(user_id=user_uuid, ticker_id=ticker_id, quantity=0, average_price=0)
        db.add(portfolio)

    # 5. 매매 로직 (공매도/스위칭 포함)
    try:
        trade_amount = current_price * quantity
        current_qty = portfolio.quantity
        
        # [매수 (BUY)]
        # 1. 롱 진입/추가 (Long Open/Add)
        # 2. 숏 청산/커버링 (Short Close/Cover)
        if trade_side == OrderSide.BUY:
            # 지갑에서 돈 차감 (숏 커버링이어도 돈은 나감)
            if wallet.balance < trade_amount:
                order.status = OrderStatus.FAILED
                order.fail_reason = f"잔고 부족 (필요: {trade_amount}, 보유: {wallet.balance})"
                db.commit()
                return False
            
            wallet.balance -= trade_amount
            
            # A. 롱 -> 롱 (불타기/물타기)
            if current_qty >= 0:
                # 평단가 갱신: (기존가치 + 신규가치) / 전체수량
                prev_total_val = current_qty * portfolio.average_price
                new_total_val = prev_total_val + trade_amount
                new_qty = current_qty + quantity
                
                portfolio.average_price = new_total_val / new_qty
                portfolio.quantity = new_qty
                
            # B. 숏 -> ? (상환 or 스위칭)
            else: # current_qty < 0
                remaining_qty = current_qty + quantity # 음수 + 양수 = 0쪽으로 이동
                
                if remaining_qty <= 0:
                    # B-1. 숏 -> 숏/0 (일부 상환 또는 완전 상환)
                    # 평단가 유지 (빚을 갚는 것이므로 평단가는 그대로)
                    portfolio.quantity = remaining_qty
                else:
                    # B-2. 숏 -> 롱 (스위칭)
                    # 숏은 다 청산하고, 남은 수량만큼 롱 신규 진입
                    # 평단가는 현재가(신규 진입 가격)로 리셋
                    portfolio.quantity = remaining_qty
                    portfolio.average_price = current_price

        # [매도 (SELL)]
        # 1. 롱 청산/이익실현 (Long Close)
        # 2. 숏 진입/추가 (Short Open/Add) - 공매도
        elif trade_side == OrderSide.SELL:
            # 지갑에 돈 입금 (공매도여도 현금 확보)
            wallet.balance += trade_amount
            
            # A. 롱 -> ? (청산 or 스위칭)
            if current_qty > 0:
                remaining_qty = current_qty - quantity
                
                if remaining_qty >= 0:
                    # A-1. 롱 -> 롱/0 (일부 매도)
                    # 평단가 유지 (이익 실현)
                    portfolio.quantity = remaining_qty
                else:
                    # A-2. 롱 -> 숏 (스위칭)
                    # 롱 다 팔고, 남은 수량만큼 숏 신규 진입
                    # 평단가는 현재가(신규 숏 진입 가격)로 리셋
                    portfolio.quantity = remaining_qty
                    portfolio.average_price = current_price
            
            # B. 숏 -> 숏 (불타기/추가 공매도)
            else: # current_qty <= 0
                # 평단가 갱신 필요! (숏 물타기)
                # 주의: 숏 수량은 음수이므로 절대값 사용 계산
                prev_total_val = abs(current_qty) * portfolio.average_price
                new_total_val = prev_total_val + trade_amount
                new_qty_abs = abs(current_qty - quantity) # 둘 다 음수 방향이므로 절대값은 더해짐
                
                portfolio.average_price = new_total_val / new_qty_abs
                portfolio.quantity -= quantity

        # 6. 마무리 (0이면 삭제할지, 말지)
        # 부동소수점 오차 고려하여 0에 가까우면 0 처리
        if abs(portfolio.quantity) <= Decimal("1e-8"):
             db.delete(portfolio)
        
        # 최종 커밋
        order.status = OrderStatus.FILLED
        order.unfilled_quantity = 0
        order.filled_at = func.now()
        db.commit()
        
        print(f"✅ Trade Executed: {side} {quantity} {ticker_id} @ {current_price}. New Qty: {portfolio.quantity if abs(portfolio.quantity) > Decimal('1e-8') else 0}")
        return True

    except Exception as e:
        db.rollback()
        print(f"❌ Trade Failed: {e}")
        order.status = OrderStatus.FAILED
        order.fail_reason = str(e)
        db.commit()
        return False