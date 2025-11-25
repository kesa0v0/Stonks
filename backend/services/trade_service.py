# backend/services/trade_service.py
import json
import redis
import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.models import User, Wallet, Portfolio, Order, OrderStatus, OrderSide, Ticker
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

    # 1. 현재가 조회 (시장가 거래 가정)
    current_price = get_current_price(ticker_id)
    if current_price is None:
        print(f"❌ Price not found for {ticker_id}")
        return False

    # 2. 유저 및 지갑 조회
    # (실제로는 없는 유저면 에러 처리해야 함. 여기선 테스트 유저 생성 로직이 필요할 수 있음)
    wallet = db.query(Wallet).filter(Wallet.user_id == user_uuid).first()
    if not wallet:
        # 지갑이 없으면 자동 생성 (테스트 편의상)
        wallet = Wallet(user_id=user_uuid, balance=100000000) # 초기자금 1억
        db.add(wallet)
        db.commit() # ID 생성을 위해 커밋
        db.refresh(wallet)

    # 3. 주문 기록 생성 (API에서 DB에 안 넣었으므로 여기서 생성)
    new_order = Order(
        id=order_uuid,
        user_id=user_uuid,
        ticker_id=ticker_id,
        side=trade_side,
        quantity=quantity,
        price=current_price,
        status=OrderStatus.PENDING
    )
    db.add(new_order)

    # 4. 매수/매도 로직
    try:
        total_cost = current_price * quantity
        
        if trade_side == OrderSide.BUY:
            # [매수] 잔고 확인
            if wallet.balance < total_cost:
                new_order.status = OrderStatus.FAILED
                new_order.fail_reason = f"잔고 부족 (필요: {total_cost}, 보유: {wallet.balance})"
                db.commit()
                print(f"⚠️ 잔고 부족으로 실패")
                return False

            # 돈 빼기
            wallet.balance -= total_cost
            
            # 주식 더하기 (포트폴리오)
            portfolio = db.query(Portfolio).filter(
                Portfolio.user_id == user_uuid, 
                Portfolio.ticker_id == ticker_id
            ).first()
            
            if not portfolio:
                portfolio = Portfolio(user_id=user_uuid, ticker_id=ticker_id, quantity=0, average_price=0)
                db.add(portfolio)
            
            # 평단가 계산 (이동평균법)
            # 기존총액 + 신규총액 / 기존수량 + 신규수량
            prev_total = portfolio.quantity * portfolio.average_price
            new_total = prev_total + total_cost
            new_quantity = portfolio.quantity + quantity
            
            portfolio.average_price = new_total / new_quantity
            portfolio.quantity = new_quantity

        elif trade_side == OrderSide.SELL:
            # [매도] 보유 수량 확인
            portfolio = db.query(Portfolio).filter(
                Portfolio.user_id == user_uuid, 
                Portfolio.ticker_id == ticker_id
            ).first()
            
            if not portfolio or portfolio.quantity < quantity:
                new_order.status = OrderStatus.FAILED
                new_order.fail_reason = "보유 수량 부족"
                db.commit()
                return False

            # 주식 빼기
            portfolio.quantity -= quantity
            # 돈 더하기
            wallet.balance += total_cost
            
            # (수량이 0이 되면 포트폴리오 삭제 로직 등을 넣을 수도 있음)

        # 5. 최종 커밋 (체결 완료)
        new_order.status = OrderStatus.FILLED
        new_order.filled_at = func.now()
        db.commit()
        print(f"✅ Trade Executed: {side} {quantity} {ticker_id} @ {current_price}")
        return True

    except Exception as e:
        db.rollback()
        print(f"❌ Trade Failed: {e}")
        new_order.status = OrderStatus.FAILED
        new_order.fail_reason = str(e)
        db.commit()
        return False