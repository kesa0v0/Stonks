# backend/app/routers/order.py
import json
import uuid
import aio_pika
from fastapi import APIRouter, Depends, HTTPException
from backend.schemas.order import OrderCreate, OrderResponse
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
async def create_order(order: OrderCreate):
    """
    주문 접수 API (Non-blocking)
    DB를 건드리지 않고 Queue에 넣기만 함.
    """
    
    # 1. 임시 주문 ID 생성 (추적용)
    order_id = str(uuid.uuid4())
    
    # 2. 메시지 페이로드 구성
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