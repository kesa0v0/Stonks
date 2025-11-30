from decimal import Decimal
from backend.models import Wallet


def set_balance(wallet: Wallet, new_balance, reason: str | None = None) -> None:
    wallet.last_update_reason = reason
    wallet.balance = Decimal(str(new_balance))


def add_balance(wallet: Wallet, delta, reason: str | None = None) -> None:
    wallet.last_update_reason = reason
    wallet.balance = (wallet.balance or Decimal("0")) + Decimal(str(delta))


def sub_balance(wallet: Wallet, delta, reason: str | None = None) -> None:
    wallet.last_update_reason = reason
    wallet.balance = (wallet.balance or Decimal("0")) - Decimal(str(delta))
