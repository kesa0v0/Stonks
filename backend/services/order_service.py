import json
import uuid
import aio_pika
import redis.asyncio as async_redis
from uuid import UUID
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core import constants
from backend.core.exceptions import (
    MarketPriceNotFoundError, 
    InsufficientSharesError, 
    InvalidLimitOrderPriceError, 
    InsufficientBalanceError, 
    OrderSystemError, 
    OrderNotFoundError, 
    PermissionDeniedError, 
    OrderNotCancellableError
)
from backend.models import Order, Portfolio, Wallet
from backend.core.enums import OrderType, OrderSide, OrderStatus
from backend.schemas.order import OrderCreate
from backend.core.config import settings

async def place_order(
    db: AsyncSession, 
    redis: async_redis.Redis, 
    user_uuid: UUID, 
    order: OrderCreate
):
    """
    주문 접수 로직
    - 유효성 검사 (잔액, 포트폴리오 등)
    - 지정가(LIMIT): DB 저장
    - 시장가(MARKET): RabbitMQ 전송
    """
    
    # 1. 임시 주문 ID 생성 (추적용)
    order_id = str(uuid.uuid4())
    
    # [검증] 유효성 체크 (공매도 방지 및 잔고 확인)
    
    # 포트폴리오 및 지갑 정보 미리 조회 (공매도 로직을 위해) - 비동기
    portfolio_result = await db.execute(
        select(Portfolio).where(
            Portfolio.user_id == user_uuid,
            Portfolio.ticker_id == order.ticker_id
        )
    )
    portfolio_item = portfolio_result.scalars().first()
    available_qty = portfolio_item.quantity if portfolio_item else Decimal(0) # Ensure Decimal
    
    wallet_result = await db.execute(select(Wallet).where(Wallet.user_id == user_uuid))
    wallet = wallet_result.scalars().first()
    balance = wallet.balance if wallet else Decimal(0) # Ensure Decimal

    # [수수료율 조회]
    fee_rate_str = await redis.get(constants.REDIS_KEY_TRADING_FEE_RATE)
    # Convert to Decimal, assuming Redis stores it as string/bytes
    fee_rate = Decimal(fee_rate_str.decode()) if fee_rate_str else Decimal(constants.DEFAULT_TRADING_FEE_RATE) 

    # [시장가 주문 사전 가격 조회]
    current_price = Decimal(0) # Use Decimal
    if order.type == OrderType.MARKET:
        price_data = await redis.get(f"{constants.REDIS_PREFIX_PRICE}{order.ticker_id}")
        if not price_data:
             raise MarketPriceNotFoundError("현재 시세 정보를 가져올 수 없습니다.")
        # Convert to Decimal
        current_price = Decimal(str(json.loads(price_data)['price']))

    # 1) 매도(SELL) 주문 시 검증
    if order.side == OrderSide.SELL:
        # A. 롱 포지션 청산 (보유 수량 > 0)
        if available_qty > Decimal(0):
            if available_qty < order.quantity:
                raise InsufficientSharesError(float(available_qty), float(order.quantity), f"보유 수량이 부족하여 매도할 수 없습니다. (보유: {available_qty}, 요청: {order.quantity})")
        # B. 공매도 (보유 수량 <= 0 또는 숏 포지션)
        else:
            required_margin = Decimal(0) # Use Decimal
            
            # 지정가 공매도
            if order.type == OrderType.LIMIT:
                if not order.target_price or order.target_price <= Decimal(0):
                     raise InvalidLimitOrderPriceError("지정가 주문에는 유효한 목표 가격이 필요합니다.")
                required_margin = order.target_price * order.quantity
            
            # STOP_LOSS 공매도 (Stop Sell)
            elif order.type == OrderType.STOP_LOSS:
                if not order.stop_price or order.stop_price <= Decimal(0):
                     raise InvalidLimitOrderPriceError("STOP_LOSS 주문에는 유효한 감시 가격(stop_price)이 필요합니다.")
                # 스탑로스는 트리거되면 시장가로 매도됨. 증거금 계산은 스탑 가격 기준으로 하거나 현재가 기준으로 보수적으로 잡음
                # 여기서는 Stop Price가 트리거 가격이므로 보수적으로 Min(현재가, 스탑가)로 잡을 수도 있지만,
                # 보통 Stop Sell은 현재가보다 낮게 잡으므로(손절), 스탑가 기준으로 증거금을 잡는게 논리적일 수 있음.
                # 하지만 Stop Sell이 트리거 되는 순간 시장가이므로 슬리피지가 발생할 수 있음.
                # 간단히 stop_price로 계산.
                required_margin = order.stop_price * order.quantity

            # 시장가 공매도
            elif order.type == OrderType.MARKET:
                required_margin = current_price * order.quantity

            # 공매도 증거금에는 수수료 포함 안 함 (매도 시 돈이 들어오므로)
            if balance < required_margin:
                 raise InsufficientBalanceError(float(required_margin), float(balance), message=f"공매도 증거금이 부족합니다. (필요: {required_margin}, 보유: {balance})")

    # 2) 매수(BUY) 주문 시 검증
    elif order.side == OrderSide.BUY:
        required_amount = Decimal(0) # Use Decimal
        
        # 지정가 매수
        if order.type == OrderType.LIMIT:
            if not order.target_price or order.target_price <= Decimal(0):
                 raise InvalidLimitOrderPriceError("지정가 주문에는 유효한 목표 가격이 필요합니다.")
            required_amount = (order.target_price * order.quantity) * (Decimal(1) + fee_rate) # Use Decimal(1)
            
        # STOP_LOSS 매수 (Stop Buy)
        elif order.type == OrderType.STOP_LOSS:
            if not order.stop_price or order.stop_price <= Decimal(0):
                 raise InvalidLimitOrderPriceError("STOP_LOSS 주문에는 유효한 감시 가격(stop_price)이 필요합니다.")
            # Stop Buy: 가격이 오르면 매수. 보통 현재가보다 높게 설정.
            required_amount = (order.stop_price * order.quantity) * (Decimal(1) + fee_rate)

        # 시장가 매수
        elif order.type == OrderType.MARKET:
            required_amount = (current_price * order.quantity) * (Decimal(1) + fee_rate) # Use Decimal(1)

        if balance < required_amount:
             raise InsufficientBalanceError(float(required_amount), float(balance), message=f"매수 잔액이 부족합니다 (수수료 {fee_rate*Decimal(100)}% 포함). (필요: {required_amount}, 보유: {balance})")

    # [분기 1] 지정가(LIMIT) 또는 스탑로스(STOP_LOSS) 주문인 경우 -> DB에 저장만 하고 끝냄 (매칭 대기)
    if order.type in [OrderType.LIMIT, OrderType.STOP_LOSS]:
        target_price = order.target_price
        if order.type == OrderType.LIMIT:
            if not target_price or target_price <= Decimal(0):
                 raise InvalidLimitOrderPriceError("지정가 주문에는 유효한 목표 가격이 필요합니다.")
        elif order.type == OrderType.STOP_LOSS:
            # Stop-Loss 주문은 target_price 대신 stop_price를 사용하거나 별도 컬럼에 저장
            # 여기서는 stop_price가 필수
            if not order.stop_price or order.stop_price <= Decimal(0):
                 raise InvalidLimitOrderPriceError("STOP_LOSS 주문에는 유효한 감시 가격이 필요합니다.")

        new_order = Order(
            id=uuid.UUID(order_id),
            user_id=user_uuid,
            ticker_id=order.ticker_id,
            side=order.side,
            type=order.type,
            status=OrderStatus.PENDING, # 대기 상태
            quantity=order.quantity,
            unfilled_quantity=order.quantity, # 초기엔 100% 미체결
            target_price=order.target_price, # LIMIT일 때만 값 있음
            stop_price=order.stop_price, # STOP_LOSS일 때만 값 있음
            price=None # 아직 체결 안 됨
        )
        db.add(new_order)
        await db.commit() # 비동기 커밋
        
        msg = f"Limit order placed at {order.target_price}" if order.type == OrderType.LIMIT else f"Stop-Loss order placed at {order.stop_price}"
        return {
            "order_id": order_id,
            "status": "PENDING",
            "message": msg
        }
    
    # 2. 메시지 페이로드 구성. 시장가(MARKET) 주문인 경우 -> 기존처럼 RabbitMQ로 전송
    message_body = {
        "order_id": order_id,
        "user_id": str(user_uuid), # UUID -> str 변환
        "ticker_id": order.ticker_id,
        "side": order.side, 
        "quantity": float(order.quantity) # Float for message body
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
        raise OrderSystemError(str(e))

    return {
        "order_id": order_id,
        "status": "ACCEPTED",
        "message": "Order has been queued for processing."
    }

async def cancel_order_logic(
    db: AsyncSession,
    user_uuid: UUID,
    order_id: UUID
):
    """
    PENDING 상태의 지정가 주문을 취소합니다. 주문 소유자만 취소 가능.
    """
    # 주문 조회
    result = await db.execute(select(Order).where(Order.id == order_id))
    order_obj = result.scalars().first()

    if not order_obj:
        raise OrderNotFoundError("주문을 찾을 수 없습니다.")

    # 소유자 확인
    if str(order_obj.user_id) != str(user_uuid):
        raise PermissionDeniedError("권한이 없습니다.")

    # 상태 확인: PENDING만 취소 가능
    if order_obj.status != OrderStatus.PENDING:
        raise OrderNotCancellableError(str(order_obj.status), f"취소 불가한 주문 상태입니다: {order_obj.status}")

    # 취소 처리
    order_obj.status = OrderStatus.CANCELLED
    order_obj.fail_reason = "Cancelled by user"
    order_obj.cancelled_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "order_id": str(order_id),
        "status": "CANCELLED",
        "message": "Order has been cancelled."
    }
