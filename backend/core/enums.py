from enum import Enum

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"     # 시장가 손절 (Stop-Market)
    TAKE_PROFIT = "TAKE_PROFIT" # 시장가 익절 (Take-Profit Market)
    STOP_LIMIT = "STOP_LIMIT"   # 예약 지정가 (Stop triggers Limit)
    TRAILING_STOP = "TRAILING_STOP" # 이동식 손절매

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(str, Enum):
    PENDING = "PENDING"   # 매칭 대기중
    TRIGGERED = "TRIGGERED" # 예약 주문 발동됨 (Stop-Limit 등에서 사용)
    FILLED = "FILLED"     # 체결 완료
    CANCELLED = "CANCELLED" # 취소됨
    FAILED = "FAILED"     # 실패
    ACCEPTED = "ACCEPTED" # 접수됨
