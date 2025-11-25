# backend/models/__init__.py
from backend.core.database import Base
from .user import User, Wallet
from .asset import Ticker, Portfolio, MarketType, Currency
from .order import Order, OrderStatus, OrderSide

# 이것들을 expose 해야 Alembic이나 create_all이 인식함
__all__ = [
    "Base",
    "User", "Wallet",
    "Ticker", "Portfolio", "MarketType", "Currency",
    "Order", "OrderStatus", "OrderSide"
]