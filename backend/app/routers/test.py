import json
import redis.asyncio as redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.core.config import settings

router = APIRouter(prefix="/test", tags=["test"])

class PriceUpdate(BaseModel):
    ticker_id: str
    price: float

@router.post("/price")
async def set_test_price(update: PriceUpdate):
    """
    [테스트용] 특정 코인의 가격을 강제로 변경하고 이벤트를 발생시킵니다.
    이 API를 호출하면 limit_matcher가 즉시 반응하여 지정가 주문을 체결합니다.
    """
    
    # 1. Redis 연결
    r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)
    
    try:
        # 2. Redis에 현재가 저장 (Key: price:{ticker_id})
        # 실제 시스템이 사용하는 키 형식에 맞춤
        price_data = {
            "ticker_id": update.ticker_id,
            "price": update.price,
            "timestamp": "TEST_MANUAL_UPDATE"
        }
        await r.set(f"price:{update.ticker_id}", json.dumps(price_data))
        
        # 3. Pub/Sub 메시지 발행 (Channel: market_updates)
        # limit_matcher가 이 채널을 구독하고 있음
        await r.publish("market_updates", json.dumps(price_data))
        
        return {"status": "ok", "message": f"Price of {update.ticker_id} set to {update.price}"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await r.close()