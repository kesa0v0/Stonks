# backend/app/main.py
import asyncio
import json
import redis.asyncio as redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from backend.core.config import settings
from backend.core.database import Base, engine, wait_for_db
from sqlalchemy import text
from backend.create_test_user import create_test_user
from backend.create_tickers import init_tickers
from backend.app.routers import market, order, auth, admin, api_key, me

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic replacing deprecated on_event
    try:
        # 1. DB 연결 대기
        await wait_for_db()

        # 2. 테이블 생성 (Alembic을 쓰지만 개발 편의를 위해 남겨둘 수 있음. 
        #    단, Alembic이 있으면 보통 생략하거나 Alembic을 호출함. 여기선 안전하게 유지)
        #    * Alembic 사용 시에는 이 라인을 지워도 되지만, 초기 개발 시 편리함을 위해 둠.
        #    * 단, Alembic revision이 꼬일 수 있으니 주의.
        # async with engine.begin() as conn:
        #     await conn.run_sync(Base.metadata.create_all)
        
        # if settings.DEBUG:
        #     print("[lifespan] DB tables ensured (create_all)")
        
        if settings.DEBUG:
            try:
                # 데이터 시딩
                tasks = [create_test_user(), init_tickers()]
                await asyncio.gather(*tasks)
                print("[lifespan] Dev seed completed (test user, tickers)")
            except Exception as se:
                print(f"[lifespan] Dev seed failed: {se}")
    except Exception as e:
        print(f"[lifespan] Startup failure: {e}")
        # DB 연결 실패 시 앱 구동을 멈추려면 여기서 raise e
    
    # Yield control to allow application to serve
    yield
    # Shutdown logic (none yet; placeholder for future resource cleanup)
    if settings.DEBUG:
        print("[lifespan] Shutdown complete")

# API Docs 태그 순서 정의
tags_metadata = [
    {"name": "auth", "description": "Authentication"},
    {"name": "me", "description": "User Profile, Portfolio & PnL"},
    {"name": "order", "description": "Order Management"},
    {"name": "market", "description": "Market Data (Ticker, Candle, Price)"},
    {"name": "admin", "description": "Admin Operations"},
    {"name": "api_key", "description": "API Key Management"},
]

app = FastAPI(
    title="Stonk Server API",
    description="Stock & Crypto Trading Simulation Platform",
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=tags_metadata # 태그 순서 적용
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
app.include_router(me.router) # 순서: Auth -> Me -> Order -> Market
app.include_router(order.router)
app.include_router(market.router)
app.include_router(admin.router)
app.include_router(api_key.router)

# --- Custom OpenAPI to include API Key security scheme ---
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    security_schemes = openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})
    # Add API Key scheme (header based) if not present
    security_schemes.setdefault("ApiKeyAuth", {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "Provide the API Key issued via /api-keys endpoint"
    })
    # Existing Bearer may already be auto-generated by OAuth2PasswordBearer; keep both
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Removed deprecated on_event startup handler; migrated to lifespan above.