# API별 rate limit 설정을 한 곳에서 관리
from fastapi_limiter.depends import RateLimiter

# 엔드포인트별 rate limit 설정 (경로: 제한)
API_RATE_LIMITS = {
    # 주문 관련
    "/orders": {"times": 5, "seconds": 1},
    "/orders/{order_id}/cancel": {"times": 10, "seconds": 1},

    # 인증/토큰
    "/login/me": {"times": 20, "seconds": 10},
    "/login/access-token": {"times": 10, "seconds": 10},
    "/login/refresh": {"times": 5, "seconds": 10},
    "/logout": {"times": 10, "seconds": 10},

    # 내 정보
    "/me/portfolio": {"times": 20, "seconds": 5},
    "/me/pnl": {"times": 20, "seconds": 5},
    "/me/orders": {"times": 20, "seconds": 5},
    "/me/orders/open": {"times": 20, "seconds": 5},
    "/me/orders/{order_id}": {"times": 20, "seconds": 5},
    "/me/bankruptcy": {"times": 2, "seconds": 60},

    # 마켓
    "/market/status": {"times": 30, "seconds": 5},
    "/market/tickers": {"times": 30, "seconds": 5},
    "/market/search": {"times": 30, "seconds": 5},
    "/market/candles/{ticker_id}": {"times": 30, "seconds": 5},
    "/market/orderbook/{ticker_id}": {"times": 30, "seconds": 5},
    "/market/price/{ticker_id}": {"times": 30, "seconds": 5},
    "/market/price-any/{ticker_id}": {"times": 30, "seconds": 5},

    # 랭킹
    "/rankings/seasons": {"times": 10, "seconds": 10},
    "/rankings/hall-of-fame": {"times": 10, "seconds": 10},
    "/rankings/{ranking_type}": {"times": 20, "seconds": 10},

    # 휴먼 ETF
    "/human/bailout": {"times": 2, "seconds": 60},
    "/human/ipo": {"times": 2, "seconds": 60},
    "/human/burn": {"times": 5, "seconds": 60},

    # 관리자
    "/admin/fee": {"times": 10, "seconds": 60},
    "/admin/price": {"times": 5, "seconds": 60},
    "/admin/tickers": {"times": 5, "seconds": 60},
    "/admin/tickers/{ticker_id}": {"times": 5, "seconds": 60},

    # API Key 관리
    "/api-keys/create": {"times": 5, "seconds": 60},
    "/api-keys/list": {"times": 10, "seconds": 60},
    "/api-keys/revoke": {"times": 5, "seconds": 60},
    "/api-keys/rotate": {"times": 5, "seconds": 60},
}

def get_rate_limiter(path: str):
    conf = API_RATE_LIMITS.get(path)
    if conf:
        return RateLimiter(times=conf["times"], seconds=conf["seconds"])
    return None
