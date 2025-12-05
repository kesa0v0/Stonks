from decimal import Decimal

# --- Redis Keys ---
REDIS_KEY_TRADING_FEE_RATE = "config:trading_fee_rate"
REDIS_KEY_WHALE_THRESHOLD_KRW = "config:whale_threshold_krw"
REDIS_PREFIX_PRICE = "price:"
REDIS_PREFIX_REFRESH = "refresh:"
REDIS_PREFIX_BLACKLIST = "blacklist:"

# --- Redis Channels ---
REDIS_CHANNEL_MARKET_UPDATES = "market_updates"

# --- Game Balance (Human ETF) ---
HUMAN_BAILOUT_BASE_AMOUNT = 100000  # 100,000 KRW
HUMAN_BAILOUT_PENALTY_PER_COUNT = 0.2  # 20%
HUMAN_DIVIDEND_RATE_MIN = 0.5
HUMAN_DIVIDEND_RATE_NORMAL_MIN = 0.1
HUMAN_BURN_THRESHOLD = Decimal("1e-8")
HUMAN_DELIST_THRESHOLD = Decimal("1e-8")
HUMAN_STOCK_ISSUED_ON_BANKRUPTCY = 1000
HUMAN_IPO_FEE = 10000000 # 1,000만 KRW

# --- API Key ---
API_KEY_LENGTH = 40
API_KEY_PREFIX_LENGTH = 12

# --- Margin / Liquidation ---
MARGIN_MAINTENANCE_RATE = Decimal("0.05")  # 순자산이 공매도 평가액의 5% 미만이면 청산

# --- Defaults ---
DEFAULT_TRADING_FEE_RATE = "0.001"
DEFAULT_WHALE_THRESHOLD_KRW = "10000000"  # 1,000만 KRW

# --- Message Template Keys ---
TEMPLATE_KEYS = [
	"whale_trade",
	"liquidation",
	"ipo_listed",
	"dividend_paid",
	"bailout_processed",
	"daily_report",
]

REDIS_PREFIX_TEMPLATE = "config:msg_template:"

DEFAULT_TEMPLATES = {
	"whale_trade": "🐳 [고래] {nickname}님이 {ticker}에 {notional:,} KRW 규모 {side} 체결!",
	"liquidation": "📉 [속보] {nickname}님이 {ticker} 포지션 강제 청산! (순자산 {equity:,} / 부채 {liability:,})",
	"ipo_listed": "🆕 [IPO] {symbol} 상장! 배당률 {dividend_rate_pct}%",
	"dividend_paid": "💰 [배당] {payer_nickname}님이 총 {total_dividend:,} KRW 배당",
	"bailout_processed": "😭 [파산] {nickname}님 구제금융 처리",
	"daily_report": (
		"📊 일일 리포트\n"
		"🥇 오늘의 승리자: {gainer_nickname} (+{gainer_pnl:,} KRW)\n"
		"💩 오늘의 흑우: {loser_nickname} ({loser_pnl:,} KRW)\n"
		"🌙 야수의 심장: {volume_king_nickname} ({trade_count}회 체결)"
	),
}

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
