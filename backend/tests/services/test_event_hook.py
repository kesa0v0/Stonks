import pytest
import asyncio
import json
from unittest.mock import AsyncMock
import sqlalchemy
from decimal import Decimal
from backend.services.trade_service import execute_trade
from backend.core.event_hook import publish_event

class DummyRedis:
    def __init__(self):
        self.published = []
    async def publish(self, channel, message):
        self.published.append((channel, message))

@pytest.mark.asyncio
async def test_post_trade_event_hook(monkeypatch):
    class DummyUser:
        def __init__(self):
            self.dividend_rate = 0.0
    dummy_user = DummyUser()
    # Dummy DB, Redis, 기타 파라미터 준비
    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    redis_client = DummyRedis()
    user_id = "11111111-1111-1111-1111-111111111111"
    order_id = "22222222-2222-2222-2222-222222222222"
    ticker_id = "AAPL"
    side = "BUY"
    quantity = Decimal("1.0")


    monkeypatch.setattr("backend.services.trade_service.get_current_price", AsyncMock(return_value=Decimal("100.0")))
    monkeypatch.setattr("backend.services.trade_service.get_trading_fee_rate", AsyncMock(return_value=Decimal("0.01")))
    # Provide a lightweight fake Statement object that implements
    # `.where()` and `.with_for_update()` and stringifies to include
    # the model name so our dummy_execute can detect which model is queried.
    class FakeStmt:
        def __init__(self, model):
            self.model = model
        def where(self, *a, **k):
            return self
        def with_for_update(self):
            return self
        def __str__(self):
            return f"Select({getattr(self.model, '__name__', str(self.model))})"

    monkeypatch.setattr(
        "backend.services.trade_service.select",
        lambda *a, **k: FakeStmt(a[0]) if a else FakeStmt(None),
    )
    monkeypatch.setattr("backend.services.trade_service.update_user_persona", AsyncMock())
    monkeypatch.setattr("backend.services.trade_service.func", AsyncMock())

    class DummyOrderBook:
        def __init__(self):
            self.asks = []
            self.bids = []
    
    monkeypatch.setattr("backend.services.market_service.get_orderbook_data", AsyncMock(return_value=DummyOrderBook()))

    # 더미 모델 객체 생성
    from backend.core.enums import OrderStatus, OrderType, OrderSide


    class DummyWallet:
        def __init__(self):
            self.balance = Decimal("10000.0")

    class DummyOrder:
        def __init__(self):
            self.status = OrderStatus.PENDING
            self.realized_pnl = Decimal("0.0")
            self.type = OrderType.MARKET
            self.unfilled_quantity = Decimal("0.0")
            self.filled_at = None
            self.price = Decimal("100.0")
            self.fail_reason = None

    class DummyPortfolio:
        def __init__(self, user_id, ticker_id):
            self.quantity = Decimal("0.0")
            self.average_price = Decimal("0.0")
            self.ticker_id = ticker_id
            self.user_id = user_id

    class DummyTicker:
        def __init__(self, ticker_id):
            self.id = ticker_id
            from backend.models.asset import MarketType # Import MarketType locally to avoid circular deps
            self.market_type = MarketType.US # Changed STOCK to US


    dummy_wallet = DummyWallet()
    dummy_order = DummyOrder()
    dummy_portfolio = DummyPortfolio(user_id, ticker_id)

    # db.execute가 scalars().first()로 더미 객체 반환하도록 모킹
    async def dummy_execute(stmt):
        class DummyResult:
            def scalars(self):
                class DummyScalar:
                    def first(self):
                        stmt_str = str(stmt)
                        if "Wallet" in stmt_str:
                            return dummy_wallet
                        elif "Order" in stmt_str:
                            return dummy_order
                        elif "Portfolio" in stmt_str:
                            return dummy_portfolio
                        elif "User" in stmt_str:
                            return dummy_user
                        elif "Ticker" in stmt_str:
                            return DummyTicker(ticker_id) # Return a dummy ticker
                        else:
                            return None
                return DummyScalar()
        return DummyResult()
    db.execute.side_effect = dummy_execute

    # execute_trade 실행
    result = await execute_trade(db, redis_client, user_id, order_id, ticker_id, side, quantity)
    assert result[0] is True

    # 이벤트가 정상적으로 발행됐는지 확인
    assert len(redis_client.published) == 1
    channel, message = redis_client.published[0]
    assert channel == "trade_events"
    event = json.loads(message)
    assert event["type"] == "trade_executed"
    assert event["user_id"] == user_id
    assert event["ticker_id"] == ticker_id
    assert event["side"] == side
    assert Decimal(event["quantity"]) == quantity
