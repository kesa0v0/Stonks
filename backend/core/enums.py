from enum import Enum

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(str, Enum):
    PENDING = "PENDING"   # 매칭 대기중 (지정가)
    FILLED = "FILLED"     # 체결 완료
    CANCELLED = "CANCELLED" # 취소됨 (사용자 or 시스템)
    FAILED = "FAILED"     # 실패 (잔고 부족 등)
    ACCEPTED = "ACCEPTED" # 접수됨 (시장가 -> 대기열)