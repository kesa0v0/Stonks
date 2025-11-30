from decimal import Decimal

# --- Redis Keys ---
REDIS_KEY_TRADING_FEE_RATE = "config:trading_fee_rate"
REDIS_PREFIX_PRICE = "price:"
REDIS_PREFIX_REFRESH = "refresh:"
REDIS_PREFIX_BLACKLIST = "blacklist:"

# --- Redis Channels ---
REDIS_CHANNEL_MARKET_UPDATES = "market_updates"

# --- Game Balance (Human ETF) ---
HUMAN_BAILOUT_BASE_AMOUNT = 100000  # 100,000 KRW
HUMAN_BAILOUT_PENALTY_PER_COUNT = 0.2  # 20%
HUMAN_DIVIDEND_RATE_MIN = 0.5
HUMAN_BURN_THRESHOLD = Decimal("1e-8")
HUMAN_DELIST_THRESHOLD = Decimal("1e-8")
HUMAN_STOCK_ISSUED_ON_BANKRUPTCY = 1000

# --- API Key ---
API_KEY_LENGTH = 40
API_KEY_PREFIX_LENGTH = 12

# --- Margin / Liquidation ---
MARGIN_MAINTENANCE_RATE = Decimal("0.05")  # 순자산이 공매도 평가액의 5% 미만이면 청산

# --- Defaults ---
DEFAULT_TRADING_FEE_RATE = "0.001"

# --- Wallet Audit Reasons (standardized) ---
WALLET_REASON_DEPOSIT = "deposit"
WALLET_REASON_WITHDRAW = "withdraw"
WALLET_REASON_TRADE_BUY = "trade:buy"
WALLET_REASON_TRADE_SELL = "trade:sell"
WALLET_REASON_DIVIDEND = "dividend"
WALLET_REASON_SEASON_REWARD = "season:reward"
WALLET_REASON_HUMAN_DISTRIBUTION = "human:distribution"
WALLET_REASON_LIQUIDATION_RESET = "liquidation:reset"
WALLET_REASON_FEE = "fee"
WALLET_REASON_ADJUSTMENT = "adjustment"
