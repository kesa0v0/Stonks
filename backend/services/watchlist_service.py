from uuid import UUID
from typing import List
import redis.asyncio as async_redis
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from backend.repository.watchlist import watchlist_repo
from backend.services.common.price import get_current_price
from backend.schemas.watchlist import WatchlistItemResponse
from backend.models.watchlist import Watchlist

async def add_watchlist_item(db: AsyncSession, user_id: UUID, ticker_id: str) -> Watchlist:
    # Check if already exists
    exists = await watchlist_repo.get_by_user_and_ticker(db, user_id, ticker_id)
    if exists:
        raise HTTPException(status_code=400, detail="Ticker already in watchlist")
    
    try:
        return await watchlist_repo.create(db, user_id, ticker_id)
    except IntegrityError:
        # Likely ticker_id does not exist
        raise HTTPException(status_code=404, detail="Ticker not found")
    except Exception as e:
        raise e

async def remove_watchlist_item(db: AsyncSession, user_id: UUID, ticker_id: str):
    success = await watchlist_repo.delete(db, user_id, ticker_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found in watchlist")
    return {"message": "Ticker removed from watchlist"}

async def get_user_watchlist(db: AsyncSession, user_id: UUID, redis: async_redis.Redis) -> List[WatchlistItemResponse]:
    items = await watchlist_repo.get_by_user(db, user_id)
    
    response = []
    for item in items:
        current_price_decimal = await get_current_price(redis, item.ticker_id)
        current_price = float(current_price_decimal) if current_price_decimal else 0.0
        
        # Ensure ticker.source is converted to string if it's an Enum
        # Pydantic V2 might handle it, but to be safe we can let Pydantic do its job
        # or explicit conversion if needed.
        # We rely on TickerResponse(from_attributes=True) to handle ORM -> Model
        
        response.append(WatchlistItemResponse(
            ticker=item.ticker, 
            current_price=current_price
        ))
        
    return response
