# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.core.config import settings
from backend.app.routers import order, portfolio

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


app.include_router(order.router)
app.include_router(portfolio.router)