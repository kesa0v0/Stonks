# backend/models/__init__.py
from .user import User, Wallet
from .asset import Ticker, Portfolio, MarketType, Currency, TickerSource
from .order import Order, OrderStatus, OrderSide, OrderType
from .api_key import ApiKey
from .candle import Candle
from .ranking import UserPersona
from .dividend import DividendHistory
from .vote import VoteProposal, Vote, VoteProposalStatus, VoteProposalType
from .season import Season
from .wallet_transaction_history import WalletTransactionHistory
from .order_status_history import OrderStatusHistory
from .portfolio_history import PortfolioHistory
from .watchlist import Watchlist
from .guestbook import GuestbookEntry
from backend.core.database import Base


# 이것들을 expose 해야 Alembic이나 create_all이 인식함
__all__ = [
    "Base",
    "User", "Wallet",
    "Ticker", "Portfolio", "MarketType", "Currency", "TickerSource",
    "Order", "OrderStatus", "OrderSide", "OrderType",
    "ApiKey",
    "Candle",
    "UserPersona",
    "DividendHistory",
    "VoteProposal", "Vote", "VoteProposalStatus", "VoteProposalType",
    "Season",
    "WalletTransactionHistory",
    "OrderStatusHistory",
    "PortfolioHistory",
    "Watchlist",
    "GuestbookEntry",
]