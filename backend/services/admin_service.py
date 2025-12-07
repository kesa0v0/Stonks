import json
import redis.asyncio as async_redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from backend.core import constants
from backend.core.config import settings
from backend.core.exceptions import TickerAlreadyExistsError, TickerNotFoundError
from backend.models import Ticker, User
from backend.schemas.market import TickerCreate, TickerUpdate, TickerResponse
from backend.schemas.admin import FeeUpdate, PriceUpdate, WhaleThresholdUpdate, MessageTemplateUpdate
from backend.schemas.user import UserResponse
from uuid import UUID
from typing import List

from backend.services.common.config import get_trading_fee_rate, get_message_template, set_message_template, list_all_templates
from backend.services.user_service import process_bankruptcy

async def get_current_trading_fee(redis_client: async_redis.Redis) -> dict:
    """
    현재 거래 수수료율을 조회합니다.
    """
    fee_rate = await get_trading_fee_rate(redis_client)
    return {"fee_rate": float(fee_rate)}

async def update_trading_fee_config(redis_client: async_redis.Redis, fee_update: FeeUpdate) -> dict:
    """
    거래 수수료율을 수정합니다.
    """
    await redis_client.set(constants.REDIS_KEY_TRADING_FEE_RATE, str(fee_update.fee_rate))
    return {
        "message": "Trading fee rate updated successfully",
        "fee_rate": fee_update.fee_rate
    }

async def get_current_whale_threshold(redis_client: async_redis.Redis) -> dict:
    """현재 고래 알림 임계치(KRW) 조회"""
    val = await redis_client.get(constants.REDIS_KEY_WHALE_THRESHOLD_KRW)
    if val:
        if isinstance(val, bytes):
            val = val.decode()
        return {"whale_threshold_krw": int(val)}
    return {"whale_threshold_krw": int(constants.DEFAULT_WHALE_THRESHOLD_KRW)}

async def update_whale_threshold(redis_client: async_redis.Redis, update: WhaleThresholdUpdate) -> dict:
    """고래 알림 임계치(KRW) 업데이트"""
    await redis_client.set(constants.REDIS_KEY_WHALE_THRESHOLD_KRW, str(int(update.whale_threshold_krw)))
    return {"message": "Whale threshold updated", "whale_threshold_krw": int(update.whale_threshold_krw)}

async def set_admin_test_price(redis_client: async_redis.Redis, update: PriceUpdate):
    """
    [관리자용] 특정 코인의 가격을 강제로 변경하고 이벤트를 발생시킵니다.
    """
    if settings.ENVIRONMENT == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This function is disabled in production environment."
        )

    price_data = {
        "ticker_id": update.ticker_id,
        "price": update.price,
        "timestamp": "ADMIN_MANUAL_UPDATE"
    }
    await redis_client.set(f"{constants.REDIS_PREFIX_PRICE}{update.ticker_id}", json.dumps(price_data))
    await redis_client.publish(constants.REDIS_CHANNEL_MARKET_UPDATES, json.dumps(price_data))
    return {"status": "ok", "message": f"Price of {update.ticker_id} set to {update.price}"}

async def create_new_ticker(db: AsyncSession, ticker_in: TickerCreate) -> Ticker:
    """
    새로운 종목을 추가합니다.
    """
    existing = await db.execute(select(Ticker).where(Ticker.id == ticker_in.id))
    if existing.scalars().first():
        raise TickerAlreadyExistsError(f"Ticker ID {ticker_in.id} already exists.")

    ticker = Ticker(
        id=ticker_in.id, # 입력받은 id 사용
        **ticker_in.model_dump(exclude={"id"})
    )
    db.add(ticker)
    await db.commit()
    await db.refresh(ticker)
    return ticker

async def update_existing_ticker(db: AsyncSession, ticker_id: str, ticker_in: TickerUpdate) -> Ticker:
    """
    종목 정보를 수정합니다.
    """
    result = await db.execute(select(Ticker).where(Ticker.id == ticker_id))
    ticker = result.scalars().first()
    
    if not ticker:
        raise TickerNotFoundError()
    
    update_data = ticker_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(ticker, key, value)
        
    await db.commit()
    await db.refresh(ticker)
    return ticker

async def delete_existing_ticker(db: AsyncSession, ticker_id: str):
    """
    종목을 삭제합니다.
    """
    result = await db.execute(select(Ticker).where(Ticker.id == ticker_id))
    ticker = result.scalars().first()
    
    if not ticker:
        raise TickerNotFoundError()
        
    await db.delete(ticker)
    await db.commit()
    
    return {"message": f"Ticker {ticker_id} deleted successfully"}

async def get_all_users(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[User]:
    """
    전체 유저 목록을 조회합니다.
    """
    result = await db.execute(select(User).offset(skip).limit(limit))
    return result.scalars().all()

async def force_user_bankruptcy(db: AsyncSession, redis_client: async_redis.Redis, user_id: UUID):
    """
    유저를 강제로 파산 처리합니다.
    """
    return await process_bankruptcy(db, user_id, redis_client, force=True)

async def post_system_notice(redis_client: async_redis.Redis, message: str):
    """
    전체 공지사항을 Redis에 게시합니다.
    """
    await redis_client.set("system_notice", message)
    # 필요한 경우 Pub/Sub으로 실시간 전파 가능
    return {"message": "Notice posted", "content": message}

async def update_user_status(db: AsyncSession, user_id: UUID, is_active: bool):
    """
    유저의 활성 상태(Ban 여부)를 변경합니다.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise ValueError("User not found")
        
    user.is_active = is_active
    await db.commit()
    await db.refresh(user)
    
    status_msg = "Active" if is_active else "Banned"
    return {"message": f"User status updated to {status_msg}", "is_active": user.is_active}

# --- Message Templates (Redis-backed) ---
async def get_all_message_templates(redis_client: async_redis.Redis) -> dict:
    return await list_all_templates(redis_client)

async def get_one_message_template(redis_client: async_redis.Redis, key: str) -> dict:
    content = await get_message_template(redis_client, key)
    return {"key": key, "content": content}

async def update_message_template(redis_client: async_redis.Redis, update: MessageTemplateUpdate) -> dict:
    await set_message_template(redis_client, update.key, update.content)
    return {"message": "Template updated", "key": update.key, "content": update.content}
