from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from backend.schemas.common import DecimalStr

class WalletTransactionHistoryBase(BaseModel):
    prev_balance: DecimalStr
    new_balance: DecimalStr
    reason: Optional[str] = None

class WalletTransactionHistoryCreate(WalletTransactionHistoryBase):
    pass

class WalletTransactionHistoryUpdate(WalletTransactionHistoryBase):
    pass

class WalletTransactionHistory(WalletTransactionHistoryBase):
    id: UUID
    user_id: UUID
    wallet_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
