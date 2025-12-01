import asyncio
import json
import logging
import redis.asyncio as async_redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.config import settings
from backend.core import constants
from backend.core.database import AsyncSessionLocal
from backend.models import Portfolio
from backend.services.liquidation_service import check_and_liquidate_user

logger = logging.getLogger(__name__)

async def margin_watcher():
    """
    Redis Pub/Sub을 통해 가격 변동을 감지하고,
    해당 코인에 숏 포지션을 가진 유저들의 증거금을 체크하여 강제 청산합니다.
    """
    redis_client = async_redis.Redis(
        host=settings.REDIS_HOST, 
        port=settings.REDIS_PORT, 
        decode_responses=True
    )
    
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(constants.REDIS_CHANNEL_MARKET_UPDATES)
    
    logger.info("🔥 Margin Watcher Started... Waiting for market updates.")

    # 헬퍼 함수: 각 청산 작업이 고유한 DB 세션을 가지도록 함
    async def _check_and_liquidate_user_with_session(user_id: UUID, redis_client: async_redis.Redis):
        async with AsyncSessionLocal() as db:
            await check_and_liquidate_user(db, user_id, redis_client)

    try:
        async for message in pubsub.listen():
            if message['type'] == 'message':
                try:
                    data = json.loads(message['data'])
                    ticker_id = data.get('ticker_id')
                    
                    if not ticker_id:
                        continue
                        
                    # 가격이 변한 Ticker에 대해 숏 포지션을 가진 유저 조회
                    # 이 쿼리 자체는 메인 루프에서 한 번만 실행 (DB 커넥션 오버헤드 최소화)
                    async with AsyncSessionLocal() as db:
                        stmt = select(Portfolio.user_id).where(
                            Portfolio.ticker_id == ticker_id,
                            Portfolio.quantity < 0
                        ).distinct()
                        result = await db.execute(stmt)
                        user_ids = result.scalars().all()
                        
                        if user_ids:
                            logger.info(f"Checking margin for {len(user_ids)} users holding short on {ticker_id}")
                            
                            # 각 청산 작업은 독립적인 DB 세션을 사용하여 병렬 처리
                            tasks = [
                                _check_and_liquidate_user_with_session(uid, redis_client) 
                                for uid in user_ids
                            ]
                            await asyncio.gather(*tasks)
                            
                except Exception as e:
                    logger.error(f"Error processing market update: {e}", exc_info=True)
                    
    except Exception as e:
        logger.error(f"Margin Watcher crashed: {e}", exc_info=True)
    finally:
        await pubsub.close()
        await redis_client.close()

if __name__ == "__main__":
    # Standalone 실행 지원
    logging.basicConfig(level=logging.INFO)
    asyncio.run(margin_watcher())
