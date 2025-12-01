# backend/app/main.py
import asyncio
import json
import redis.asyncio as redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.core.config import settings
from backend.core import constants
from backend.core.database import Base, engine, wait_for_db
from sqlalchemy import text
from backend.create_test_user import create_test_user
from backend.create_tickers import init_tickers
from backend.app.routers import market, order, auth, admin, api_key, me, ranking, human
from backend.core.rate_limit import init_rate_limiter
from backend.core.exceptions import StonksError
from backend.app.exception_handlers import stonks_exception_handler, general_exception_handler
from prometheus_fastapi_instrumentator import Instrumentator
from backend.worker.maintenance import perform_db_backup, cleanup_old_candles

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic replacing deprecated on_event
    scheduler = AsyncIOScheduler()
    
    try:
        # fastapi-limiter 초기화 (Redis)
        await init_rate_limiter()
        # 1. DB 연결 대기
        await wait_for_db()
        
        # 2. 스케줄러 설정 (백업 & 청소)
        if settings.ENVIRONMENT != "test": # 테스트 환경에선 스킵
            # 매일 새벽 3:00 KST (UTC 18:00) - 백업
            # 여기선 간단히 서버 시간 기준 03:00으로 설정 (Docker Timezone 주의)
            scheduler.add_job(perform_db_backup, CronTrigger(hour=3, minute=0))
            
            # 매주 일요일 새벽 4:00 - 오래된 데이터 정리
            scheduler.add_job(cleanup_old_candles, CronTrigger(day_of_week='sun', hour=4, minute=0))
            
            scheduler.start()
            print("[lifespan] Scheduler started for maintenance tasks")

        # 3. 초기 데이터 시딩 (개발 환경)
        if settings.DEBUG:
            try:
                tasks = [create_test_user(), init_tickers()]
                await asyncio.gather(*tasks)
                print("[lifespan] Dev seed completed (test user, tickers)")
            except Exception as se:
                print(f"[lifespan] Dev seed failed: {se}")
                
    except Exception as e:
        print(f"[lifespan] Startup failure: {e}")
    
    # Yield control to allow application to serve
    yield
    
    # Shutdown logic
    scheduler.shutdown()
    if settings.DEBUG:
        print("[lifespan] Shutdown complete")

# API Docs 태그 순서 정의
tags_metadata = [
    {"name": "auth", "description": "Authentication"},
    {"name": "me", "description": "User Profile, Portfolio & PnL"},
    {"name": "order", "description": "Order Management"},
    {"name": "market", "description": "Market Data (Ticker, Candle, Price)"},
    {"name": "ranking", "description": "Leaderboards & Hall of Fame"},
    {"name": "human_etf", "description": "Human ETF & Bankruptcy"},
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

# Prometheus Metrics (Expose /metrics)
Instrumentator().instrument(app).expose(app)

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

app.add_exception_handler(StonksError, stonks_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

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
    await pubsub.subscribe(constants.REDIS_CHANNEL_MARKET_UPDATES) # 워커가 쏘는 채널 구독

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


app.include_router(auth.router, prefix="/api/v1/auth")
app.include_router(me.router, prefix="/api/v1")
app.include_router(order.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(ranking.router, prefix="/api/v1")
app.include_router(human.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(api_key.router, prefix="/api/v1")

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