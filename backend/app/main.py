# backend/app/main.py
import asyncio
import json
import redis.asyncio as redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from backend.core.config import settings
from backend.core.database import Base
from backend.core.database import engine
from sqlalchemy import text
from backend.create_test_user import create_test_user
from backend.create_tickers import init_tickers
from backend.app.routers import order, portfolio, test, market_data, auth, admin

app = FastAPI(
    title="Stonk Server API",
    description="Stock & Crypto Trading Simulation Platform",
    version="0.1.0"
)

# CORS 설정: 허용할 출처(Origin) 목록
origins = [
    "http://localhost:5173",      # 로컬 개발 프론트엔드
    "http://127.0.0.1:5173",      # 로컬 IP 접속 시
    "https://stock.kesa.uk",      # 나중에 배포할 도메인
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,        # 허용할 사이트들
    allow_credentials=True,       # 쿠키/인증정보 포함 허용
    allow_methods=["*"],          # 모든 HTTP Method 허용 (GET, POST...)
    allow_headers=["*"],          # 모든 Header 허용
)

@app.get("/")
def read_root():
    """서버 상태 확인용"""
    return {
        "status": "active",
        "env": "development" if settings.DEBUG else "production",
        "database_url": settings.DATABASE_URL
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}

# Redis 연결 (구독용)
# 웹소켓은 연결이 오래 유지되므로, 요청 때마다 연결하는 get_db와 달리
# 전역적인 Redis 연결 관리가 필요할 수 있지만, 여기선 간단히 엔드포인트 내에서 연결합니다.
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # 각 클라이언트마다 Redis Pub/Sub 연결 생성
    r = redis.Redis(
        host=settings.REDIS_HOST, 
        port=settings.REDIS_PORT, 
        decode_responses=True
    )
    pubsub = r.pubsub()
    await pubsub.subscribe("market_updates") # 워커가 쏘는 채널 구독

    print("🟢 Client Connected to WebSocket")

    try:
        # Redis 메시지 루프
        async for message in pubsub.listen():
            if message['type'] == 'message':
                # Redis에서 받은 데이터를 그대로 웹소켓으로 쏘기
                # data 예시: {"ticker_id": "...", "price": 123.4, "timestamp": ...}
                await websocket.send_text(message['data'])
    except WebSocketDisconnect:
        print("🔴 Client Disconnected")
    except Exception as e:
        print(f"❌ WebSocket Error: {e}")
    finally:
        await pubsub.unsubscribe()
        await pubsub.close()
        await r.close()


app.include_router(auth.router)
app.include_router(order.router)
app.include_router(portfolio.router)
app.include_router(test.router)
app.include_router(market_data.router)
app.include_router(admin.router)

# Ensure DB tables exist at startup (idempotent)
@app.on_event("startup")
async def ensure_db_tables():
    try:
        async with engine.begin() as conn:
            # Optionally set schema/search_path if needed
            # await conn.execute(text("SET search_path TO public"))
            await conn.run_sync(Base.metadata.create_all)
        if settings.DEBUG:
            print("[startup] DB tables ensured (create_all)")

        # In DEBUG, seed minimal dev data (idempotent)
        if settings.DEBUG:
            try:
                tasks = [create_test_user(), init_tickers()]
                await asyncio.gather(*tasks)
                print("[startup] Dev seed completed (test user, tickers)")
            except Exception as se:
                print(f"[startup] Dev seed failed: {se}")
    except Exception as e:
        # Log the error; in dev we continue to surface it
        print(f"[startup] Failed to ensure DB tables: {e}")