# backend/app/routers/order.py
import json
import uuid
import aio_pika
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models import Order, OrderStatus, OrderType as OrderTypeModel, Portfolio, Wallet
from backend.schemas.order import OrderCreate, OrderResponse, OrderListResponse, OrderSide, OrderType
from backend.core.config import settings

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
    db: Session = Depends(get_db)
):
    """
    주문 접수 API (Non-blocking)
    DB를 건드리지 않고 Queue에 넣기만 함.
    """
    
    # 1. 임시 주문 ID 생성 (추적용)
    order_id = str(uuid.uuid4())
    user_id = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    user_uuid = uuid.UUID(user_id)

    # [검증] 유효성 체크 (공매도 방지 및 잔고 확인)
    
    # 포트폴리오 및 지갑 정보 미리 조회 (공매도 로직을 위해)
    portfolio_item = db.query(Portfolio).filter(
        Portfolio.user_id == user_uuid,
        Portfolio.ticker_id == order.ticker_id
    ).first()
    available_qty = portfolio_item.quantity if portfolio_item else 0
    
    wallet = db.query(Wallet).filter(Wallet.user_id == user_uuid).first()
    balance = wallet.balance if wallet else 0

    # 1) 매도(SELL) 주문 시 검증
    if order.side == OrderSide.SELL:
        # A. 롱 포지션 청산 (보유 수량 > 0)
        if available_qty > 0:
            if available_qty < order.quantity:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Insufficient holdings to close long position. Available: {float(available_qty)}, Required: {float(order.quantity)}"
                )
        # B. 공매도 (보유 수량 <= 0 또는 숏 포지션) - 지정가만 API에서 체크
        elif available_qty <= 0 and order.type == OrderType.LIMIT:
            if not order.target_price or order.target_price <= 0:
                 raise HTTPException(status_code=400, detail="Limit order requires a valid target_price")
            
            required_margin = order.target_price * order.quantity
            if balance < required_margin:
                 raise HTTPException(
                    status_code=400, 
                    detail=f"Insufficient balance for short selling. Required margin: {float(required_margin)}, Available: {float(balance)}"
                )

    # 2) 매수(BUY) 지정가(LIMIT) 주문 시 잔고 확인
    # (시장가 매수는 가격을 모르므로 여기서 체크 불가 -> 체결 시 실패 처리)
    elif order.side == OrderSide.BUY and order.type == OrderType.LIMIT:
        # 숏 포지션 커버링(상환)이거나 신규 롱 진입일 수 있음.
        # 현금은 무조건 필요하므로 잔고 체크
        if not order.target_price or order.target_price <= 0:
             raise HTTPException(status_code=400, detail="Limit order requires a valid target_price")
             
        required_amount = order.target_price * order.quantity
        if balance < required_amount:
             raise HTTPException(
                status_code=400, 
                detail=f"Insufficient balance for buying. Available: {float(balance)}, Required: {float(required_amount)}"
            )

    # [분기 1] 지정가(LIMIT) 주문인 경우 -> DB에 저장만 하고 끝냄 (매칭 대기)
    # Schema Enum과 Model Enum이 다르므로 value로 비교
    if order.type.value == OrderTypeModel.LIMIT.value:
        if not order.target_price or order.target_price <= 0:
             raise HTTPException(status_code=400, detail="Limit order requires a valid target_price")

        new_order = Order(
            id=uuid.UUID(order_id),
            user_id=uuid.UUID(user_id),
            ticker_id=order.ticker_id,
            side=order.side,
            type=OrderTypeModel.LIMIT,
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
    # (실제로는 User ID도 토큰에서 가져와야 하지만, 지금은 하드코딩된 테스트 유저 ID 사용)
    # TODO: Auth 구현 후 user_id 변경 필요
    message_body = {
        "order_id": order_id,
        "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", 
        "ticker_id": order.ticker_id,
        "side": order.side,
        "quantity": float(order.quantity) # Decimal -> float 변환 (JSON 직렬화 위해)
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
def get_order_history(db: Session = Depends(get_db)):
    # 테스트 유저 ID (나중에 Auth로 교체)
    user_uuid = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6")

    orders = db.query(Order)\
        .filter(Order.user_id == user_uuid)\
        .order_by(Order.created_at.desc())\
        .limit(20)\
        .all()
    
    return orders