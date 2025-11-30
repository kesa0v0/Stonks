from uuid import UUID
import redis.asyncio as async_redis
from fastapi import APIRouter, Depends
from backend.core.rate_limit_config import get_rate_limiter
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.deps import get_current_user_id
from backend.core.cache import get_redis
from backend.schemas.order import OrderCreate, OrderResponse
from backend.services.order_service import place_order, cancel_order_logic

router = APIRouter(prefix="/orders", tags=["orders"])

@router.post("", response_model=OrderResponse, dependencies=[Depends(get_rate_limiter("/orders"))])
async def create_order(
    order: OrderCreate, 
    db: AsyncSession = Depends(get_db),
    user_uuid: UUID = Depends(get_current_user_id),
    redis: async_redis.Redis = Depends(get_redis)
):
    """
    주문 접수 API (Non-blocking)
    DB를 건드리지 않고 Queue에 넣기만 함.
    """
    return await place_order(db, redis, user_uuid, order)


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_uuid: UUID = Depends(get_current_user_id),
):
    """
    PENDING 상태의 지정가 주문을 취소합니다. 주문 소유자만 취소 가능.
    """
    return await cancel_order_logic(db, user_uuid, order_id)