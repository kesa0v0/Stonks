# backend/app/routers/order.py
import json
import uuid
import aio_pika
import redis.asyncio as async_redis
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models import Order, Portfolio, Wallet
from backend.core.enums import OrderType, OrderSide, OrderStatus
from backend.schemas.order import OrderCreate, OrderResponse, OrderListResponse
from backend.core.config import settings
from backend.core.deps import get_current_user_id
from backend.core.cache import get_redis

router = APIRouter(prefix="/orders", tags=["orders"])

# RabbitMQ 연결을 위한 의존성 주입 (Dependency Injection)
async def get_rabbitmq_channel():
    connection = await aio_pika.connect_robust(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        login=settings.RABBITMQ_USER,
        password=settings.RABBITMQ_PASS
    )
    async with connection:
        channel = await connection.channel()
        yield channel

@router.post("", response_model=OrderResponse)
async def create_order(
    order: OrderCreate, 
    db: Session = Depends(get_db),
    user_uuid: UUID = Depends(get_current_user_id),
    redis: async_redis.Redis = Depends(get_redis)
):
    """
    주문 접수 API (Non-blocking)
    DB를 건드리지 않고 Queue에 넣기만 함.
    """
    
    # 1. 임시 주문 ID 생성 (추적용)
    order_id = str(uuid.uuid4())
    # user_uuid는 Depends에서 이미 UUID 객체로 옴

    # [검증] 유효성 체크 (공매도 방지 및 잔고 확인)
    
    # 포트폴리오 및 지갑 정보 미리 조회 (공매도 로직을 위해)
    portfolio_item = db.query(Portfolio).filter(
        Portfolio.user_id == user_uuid,
        Portfolio.ticker_id == order.ticker_id
    ).first()
    available_qty = portfolio_item.quantity if portfolio_item else 0
    
    wallet = db.query(Wallet).filter(Wallet.user_id == user_uuid).first()
    balance = wallet.balance if wallet else 0

    # [수수료율 조회]
    fee_rate_str = await redis.get("config:trading_fee_rate")
    fee_rate = float(fee_rate_str) if fee_rate_str else 0.001

    # [시장가 주문 사전 가격 조회]
    current_price = 0.0
    if order.type == OrderType.MARKET:
        price_data = await redis.get(f"price:{order.ticker_id}")
        if not price_data:
             raise HTTPException(status_code=400, detail=f"Current market price unavailable for {order.ticker_id}")
        current_price = float(json.loads(price_data)['price'])

    # 1) 매도(SELL) 주문 시 검증
    if order.side == OrderSide.SELL:
        # A. 롱 포지션 청산 (보유 수량 > 0)
        if available_qty > 0:
            if available_qty < order.quantity:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Insufficient holdings to close long position. Available: {float(available_qty)}, Required: {float(order.quantity)}"
                )
        # B. 공매도 (보유 수량 <= 0 또는 숏 포지션)
        else:
            required_margin = 0.0
            
            # 지정가 공매도
            if order.type == OrderType.LIMIT:
                if not order.target_price or order.target_price <= 0:
                     raise HTTPException(status_code=400, detail="Limit order requires a valid target_price")
                required_margin = order.target_price * order.quantity
            
            # 시장가 공매도
            elif order.type == OrderType.MARKET:
                required_margin = current_price * order.quantity

            # 공매도 증거금에는 수수료 포함 안 함 (매도 시 돈이 들어오므로)
            if balance < required_margin:
                 raise HTTPException(
                    status_code=400, 
                    detail=f"Insufficient balance for short selling. Required margin: {float(required_margin)}, Available: {float(balance)}"
                )

    # 2) 매수(BUY) 주문 시 검증
    elif order.side == OrderSide.BUY:
        required_amount = 0.0
        
        # 지정가 매수
        if order.type == OrderType.LIMIT:
            if not order.target_price or order.target_price <= 0:
                 raise HTTPException(status_code=400, detail="Limit order requires a valid target_price")
            required_amount = (order.target_price * order.quantity) * (1 + fee_rate)
            
        # 시장가 매수
        elif order.type == OrderType.MARKET:
            required_amount = (current_price * order.quantity) * (1 + fee_rate)

        if balance < required_amount:
             raise HTTPException(
                status_code=400, 
                detail=f"Insufficient balance for buying (incl. fee {fee_rate*100}%). Available: {float(balance)}, Required: {float(required_amount)}"
            )

    # [분기 1] 지정가(LIMIT) 주문인 경우 -> DB에 저장만 하고 끝냄 (매칭 대기)
    if order.type == OrderType.LIMIT:
        if not order.target_price or order.target_price <= 0:
             raise HTTPException(status_code=400, detail="Limit order requires a valid target_price")

        new_order = Order(
            id=uuid.UUID(order_id),
            user_id=user_uuid,
            ticker_id=order.ticker_id,
            side=order.side,
            type=OrderType.LIMIT,
            status=OrderStatus.PENDING, # 대기 상태
            quantity=order.quantity,
            unfilled_quantity=order.quantity, # 초기엔 100% 미체결
            target_price=order.target_price,
            price=None # 아직 체결 안 됨
        )
        db.add(new_order)
        db.commit()
        
        return {
            "order_id": order_id,
            "status": "PENDING",
            "message": f"Limit order placed at {order.target_price}"
        }
    
    # 2. 메시지 페이로드 구성. 시장가(MARKET) 주문인 경우 -> 기존처럼 RabbitMQ로 전송
    message_body = {
        "order_id": order_id,
        "user_id": str(user_uuid), # UUID -> str 변환
        "ticker_id": order.ticker_id,
        "side": order.side, 
        "quantity": float(order.quantity) 
    }

    # 3. RabbitMQ 전송
    try:
        connection = await aio_pika.connect_robust(
            host=settings.RABBITMQ_HOST,
            port=settings.RABBITMQ_PORT,
            login=settings.RABBITMQ_USER,
            password=settings.RABBITMQ_PASS
        )
        async with connection:
            channel = await connection.channel()
            
            # 큐 선언 (없으면 생성)
            queue = await channel.declare_queue("trade_queue", durable=True)
            
            await channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps(message_body).encode()),
                routing_key=queue.name,
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Broker Error: {str(e)}")

    return {
        "order_id": order_id,
        "status": "ACCEPTED",
        "message": "Order has been queued for processing."
    }

@router.get("", response_model=List[OrderListResponse])
def get_order_history(
    db: Session = Depends(get_db),
    user_uuid: UUID = Depends(get_current_user_id)
):
    orders = db.query(Order)\
        .filter(Order.user_id == user_uuid)\
        .order_by(Order.created_at.desc())\
        .limit(20)\
        .all()
    
    return orders