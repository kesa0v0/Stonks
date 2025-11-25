# backend/app/main.py
from fastapi import FastAPI
from backend.core.config import settings
from backend.app.routers import order

app = FastAPI(
    title="Stonk Server API",
    description="Stock & Crypto Trading Simulation Platform",
    version="0.1.0"
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