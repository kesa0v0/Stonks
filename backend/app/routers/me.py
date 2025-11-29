import redis.asyncio as async_redis
from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from uuid import UUID

from backend.core.database import get_db
from backend.core.deps import get_current_user_id
from backend.core.cache import get_redis
from backend.schemas.portfolio import PnLResponse, PortfolioResponse
from backend.schemas.order import OrderListResponse, OrderResponse
from backend.services.user_service import (
    get_user_portfolio,
    get_user_pnl,
    get_user_orders,
    get_user_open_orders,
    get_user_order_detail,
    process_bankruptcy
)

router = APIRouter(prefix="/me", tags=["me"])

@router.get("/portfolio", response_model=PortfolioResponse)
async def get_my_portfolio(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    redis: async_redis.Redis = Depends(get_redis)
):
    """
    내 포트폴리오(보유 자산 및 현금)를 조회합니다.
    """
    return await get_user_portfolio(db, user_id, redis)

@router.get("/pnl", response_model=PnLResponse)
async def get_my_pnl(
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    특정 기간 동안의 실현 손익(Realized PnL) 합계를 조회합니다.
    """
    return await get_user_pnl(db, user_id, start, end)

@router.get("/orders", response_model=List[OrderListResponse])
async def get_my_orders(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    내 전체 주문 내역을 조회합니다.
    """
    return await get_user_orders(db, user_id)

@router.get("/orders/open", response_model=List[OrderListResponse])
async def get_my_open_orders(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    내 미체결(PENDING) 주문 내역을 조회합니다.
    """
    return await get_user_open_orders(db, user_id)

@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_my_order_detail(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """
    특정 주문의 상세 정보를 조회합니다. (본인 주문만 가능)
    """
    return await get_user_order_detail(db, user_id, order_id)


@router.post("/bankruptcy")
async def file_bankruptcy(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    redis: async_redis.Redis = Depends(get_redis)
):
    """
    [파산 신청]
    - 조건: 총 자산(현금 + 포트폴리오 평가액)이 0 이하일 때만 가능
    - 보유 자산(Portfolio) 모두 시장가에 청산
    - 미체결 주문(Pending Order) 취소
    - 유저 상태: 파산(is_bankrupt=True), 파산 횟수 증가
    - HUMAN ETF 발행: 본인 주식 1,000주 지급
    """
    return await process_bankruptcy(db, user_id, redis)
