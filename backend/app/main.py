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
from backend.app.routers import market, order, auth, admin, api_key, me, ranking, human, users, config, vote
from backend.core.rate_limit import init_rate_limiter
from backend.core.exceptions import StonksError
from backend.app.exception_handlers import stonks_exception_handler, general_exception_handler
from prometheus_fastapi_instrumentator import Instrumentator
from backend.worker.maintenance import perform_db_backup, cleanup_old_candles

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic replacing deprecated on_event
    scheduler = AsyncIOScheduler()
    
    ka_task = None
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
    {"name": "users", "description": "User Profiles"},
    {"name": "order", "description": "Order Management"},
    {"name": "market", "description": "Market Data (Ticker, Candle, Price)"},
    {"name": "ranking", "description": "Leaderboards & Hall of Fame"},
    {"name": "human_etf", "description": "Human ETF & Bankruptcy"},
    {"name": "votes", "description": "Shareholder voting"},
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
"""
Low-latency Redis → WebSocket broadcaster
Single Redis pubsub task fans out messages to connected clients via asyncio.Queue.
This avoids per-connection pubsub listeners that can lag under load.
"""
import asyncio
import redis.asyncio as async_redis
from typing import Dict, Set

class WSBridge:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.r: async_redis.Redis | None = None
        self.pubsub = None
        self.task: asyncio.Task | None = None
        self.flush_task: asyncio.Task | None = None
        self.clients: Set[asyncio.Queue] = set()
        self.lock = asyncio.Lock()
        # buffers per channel to coalesce frequent updates
        self.buffers: dict[str, dict[str, str]] = {
            "market_updates": {},
            "orderbook_updates": {},
        }

    async def start(self):
        if self.task:
            return
        self.r = async_redis.Redis(host=self.host, port=self.port, decode_responses=True)
        self.pubsub = self.r.pubsub(ignore_subscribe_messages=True)
        await self.pubsub.subscribe("market_updates", "orderbook_updates")

        async def _loop():
            try:
                while True:
                    ps = self.pubsub
                    if ps is None:
                        await asyncio.sleep(0.05)
                        continue
                    msg = await ps.get_message(timeout=0.05)
                    if msg is None:
                        await asyncio.sleep(0)
                        continue
                    if msg.get("type") == "message":
                        data = msg.get("data")
                        channel = msg.get("channel")
                        if isinstance(data, str) and channel in self.buffers:
                            try:
                                obj = json.loads(data)
                                tid = obj.get("ticker_id") or obj.get("ticker", {}).get("id")
                                if isinstance(tid, str):
                                    self.buffers[channel][tid] = data
                                    continue
                            except Exception:
                                pass
                        # Fallback: if not coalescable, broadcast immediately
                        await self._broadcast_now(data)
            except Exception as e:
                print(f"❌ WSBridge loop error: {e}")
            finally:
                try:
                    if self.pubsub:
                        await self.pubsub.unsubscribe()
                        await self.pubsub.close()
                except Exception:
                    pass
                try:
                    if self.r:
                        await self.r.aclose()
                except Exception:
                    pass

        self.task = asyncio.create_task(_loop())

        async def _flush_loop():
            try:
                while True:
                    await asyncio.sleep(0.1)
                    payloads: list[str] = []
                    # drain buffers
                    for ch in list(self.buffers.keys()):
                        bucket = self.buffers[ch]
                        if not bucket:
                            continue
                        payloads.extend(bucket.values())
                        self.buffers[ch] = {}
                    if not payloads:
                        continue
                    for data in payloads:
                        await self._broadcast_now(data)
            except Exception as e:
                print(f"❌ WSBridge flush error: {e}")

        self.flush_task = asyncio.create_task(_flush_loop())

    async def _broadcast_now(self, data: str):
        # fan out to all clients (non-blocking put_nowait with ring-buffer)
        async with self.lock:
            dead = []
            for q in list(self.clients):
                try:
                    q.put_nowait(data)
                except asyncio.QueueFull:
                    try:
                        q.get_nowait()
                        q.put_nowait(data)
                    except Exception:
                        dead.append(q)
                except Exception:
                    dead.append(q)
            for q in dead:
                self.clients.discard(q)

    async def register(self) -> asyncio.Queue:
        # each client gets a queue
        q: asyncio.Queue = asyncio.Queue(maxsize=1024)
        async with self.lock:
            self.clients.add(q)
        return q

    async def unregister(self, q: asyncio.Queue):
        async with self.lock:
            self.clients.discard(q)
        # drain queue
        try:
            while not q.empty():
                q.get_nowait()
        except Exception:
            pass

bridge = WSBridge(host=settings.REDIS_HOST, port=settings.REDIS_PORT)


# Prometheus Metrics (Expose /metrics)
Instrumentator().instrument(app).expose(app)

# CORS 설정: 허용할 출처(Origin) 목록 (환경설정에서 주입)
# DEBUG 모드일 경우 로컬 개발 편의를 위해 좀 더 관대하게 설정하거나,
# 명시된 오리진이 제대로 적용되도록 합니다.
if settings.DEBUG:
    # 개발 모드에서는 웬만하면 다 허용 (Credentials 포함 시 * 불가하므로 패턴 사용)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS, # config.py에 정의된 로컬 주소들
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:[0-9]+)?", # 로컬호스트 모든 포트 허용
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_exception_handler(StonksError, stonks_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

@app.get("/")
def read_root():
    return {
        "status": "active",
        "env": "development" if settings.DEBUG else "production",
        "database_url": settings.DATABASE_URL
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🟢 Client Connected to WebSocket")

    # Ensure bridge running
    await bridge.start()
    queue = await bridge.register()

    ka_task = None
    try:
        async def keepalive():
            while True:
                await asyncio.sleep(20)
                try:
                    await websocket.send_text("{\"type\":\"keepalive\"}")
                except Exception:
                    break

        ka_task = asyncio.create_task(keepalive())

        # Send messages from queue to this websocket
        while True:
            try:
                data = await queue.get()
            except Exception:
                break
            try:
                await websocket.send_text(data)
            except Exception:
                break
    except WebSocketDisconnect:
        print("🔴 Client Disconnected")
    except Exception as e:
        print(f"❌ WebSocket Error: {e}")
    finally:
        try:
            if ka_task:
                ka_task.cancel()
        except Exception:
            pass
        await bridge.unregister(queue)


app.include_router(auth.router, prefix="/api/v1/auth")
app.include_router(me.router, prefix="/api/v1")
app.include_router(order.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(ranking.router, prefix="/api/v1")
app.include_router(human.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(api_key.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1") # New users router
app.include_router(config.router, prefix="/api/v1")
app.include_router(vote.router, prefix="/api/v1")

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