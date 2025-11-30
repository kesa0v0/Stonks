from fastapi import APIRouter, Depends
from backend.core.rate_limit_config import get_rate_limiter
import redis.asyncio as async_redis
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.deps import get_current_admin_user
from backend.core.cache import get_redis
from backend.core.database import get_db
from backend.schemas.market import TickerCreate, TickerUpdate, TickerResponse
from backend.schemas.admin import FeeUpdate, PriceUpdate
from backend.services.admin_service import (
    get_current_trading_fee,
    update_trading_fee_config,
    set_admin_test_price,
    create_new_ticker,
    update_existing_ticker,
    delete_existing_ticker
)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_admin_user)]
)

@router.get("/fee", response_model=dict, dependencies=[Depends(get_rate_limiter("/admin/fee"))])
async def get_trading_fee(
    redis_client: async_redis.Redis = Depends(get_redis)
):
    """
    현재 거래 수수료율을 조회합니다.
    Redis에 값이 없으면 기본값(0.001, 0.1%)을 반환합니다.
    """
    return await get_current_trading_fee(redis_client)

@router.put("/fee", response_model=dict, dependencies=[Depends(get_rate_limiter("/admin/fee"))])
async def update_trading_fee(
    fee_update: FeeUpdate,
    redis_client: async_redis.Redis = Depends(get_redis)
):
    """
    거래 수수료율을 수정합니다.
    """
    return await update_trading_fee_config(redis_client, fee_update)


@router.post("/price", dependencies=[Depends(get_rate_limiter("/admin/price"))])
async def set_test_price_admin(update: PriceUpdate, redis_client: async_redis.Redis = Depends(get_redis)):
    """
    [관리자용] 특정 코인의 가격을 강제로 변경하고 이벤트를 발생시킵니다.
    이 API를 호출하면 limit_matcher가 즉시 반응하여 지정가 주문을 체결합니다.
    """
    return await set_admin_test_price(redis_client, update)

# --- Ticker Management ---

@router.post("/tickers", response_model=TickerResponse, dependencies=[Depends(get_rate_limiter("/admin/tickers"))])
async def create_ticker(
    ticker_in: TickerCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    새로운 종목을 추가합니다. ID는 `id` 필드를 통해 직접 지정합니다.
    """
    return await create_new_ticker(db, ticker_in)

@router.put("/tickers/{ticker_id}", response_model=TickerResponse, dependencies=[Depends(get_rate_limiter("/admin/tickers/{ticker_id}"))])
async def update_ticker(
    ticker_id: str,
    ticker_in: TickerUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    종목 정보를 수정합니다.
    """
    return await update_existing_ticker(db, ticker_id, ticker_in)

@router.delete("/tickers/{ticker_id}", dependencies=[Depends(get_rate_limiter("/admin/tickers/{ticker_id}"))])
async def delete_ticker(
    ticker_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    종목을 삭제합니다. (주의: 연관 데이터가 있으면 에러 발생 가능)
    """
    return await delete_existing_ticker(db, ticker_id)