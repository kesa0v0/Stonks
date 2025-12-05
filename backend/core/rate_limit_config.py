# API별 rate limit 설정을 한 곳에서 관리
from fastapi.params import Depends
from fastapi_limiter.depends import RateLimiter
from fastapi import Request
from backend.core.config import settings

# 엔드포인트별 rate limit 설정 (경로: 제한)
API_RATE_LIMITS = {
    # 주문 관련
    "/orders": {"times": 25, "seconds": 1},
    "/orders/{order_id}/cancel": {"times": 50, "seconds": 1},

    # 인증/토큰
    "/login/me": {"times": 100, "seconds": 10},
    "/login/access-token": {"times": 50, "seconds": 10},
    "/login/refresh": {"times": 25, "seconds": 10},
    "/logout": {"times": 50, "seconds": 10},

    # 내 정보
    "/me/portfolio": {"times": 100, "seconds": 5},
    "/me/pnl": {"times": 100, "seconds": 5},
    "/me/orders": {"times": 100, "seconds": 5},
    "/me/orders/open": {"times": 100, "seconds": 5},
    "/me/orders/{order_id}": {"times": 100, "seconds": 5},
    "/me/bankruptcy": {"times": 10, "seconds": 60},

    # 마켓
    "/market/status": {"times": 150, "seconds": 5},
    "/market/tickers": {"times": 150, "seconds": 5},
    "/market/search": {"times": 150, "seconds": 5},
    "/market/candles/{ticker_id}": {"times": 150, "seconds": 5},
    "/market/orderbook/{ticker_id}": {"times": 150, "seconds": 5},
    "/market/price/{ticker_id}": {"times": 150, "seconds": 5},
    "/market/price-any/{ticker_id}": {"times": 150, "seconds": 5},
    "/market/fx": {"times": 60, "seconds": 60},

    # 랭킹
    "/rankings/seasons": {"times": 50, "seconds": 10},
    "/rankings/hall-of-fame": {"times": 50, "seconds": 10},
    "/rankings/{ranking_type}": {"times": 100, "seconds": 10},

    # 휴먼 ETF
    "/human/bailout": {"times": 10, "seconds": 60},
    "/human/ipo": {"times": 10, "seconds": 60},
    "/human/burn": {"times": 25, "seconds": 60},

    # 관리자
    "/admin/fee": {"times": 50, "seconds": 1},
    "/admin/price": {"times": 25, "seconds": 1},
    "/admin/tickers": {"times": 25, "seconds": 1},
    "/admin/tickers/{ticker_id}": {"times": 25, "seconds": 1},

    # API Key 관리
    "/api-keys/create": {"times": 25, "seconds": 60},
    "/api-keys/list": {"times": 50, "seconds": 60},
    "/api-keys/revoke": {"times": 25, "seconds": 60},
    "/api-keys/rotate": {"times": 25, "seconds": 60},
}

def get_rate_limiter(path: str):
    conf = API_RATE_LIMITS.get(path)
    if not settings.RATE_LIMIT_ENABLED:
        # 비활성화 시 FastAPI가 의존성을 요구하므로 no-op 콜러블을 반환
        async def _noop_dep():
            return None
        return _noop_dep
    if conf:
        return RateLimiter(times=conf["times"], seconds=conf["seconds"])
    return None