
import pytest
import uuid
from decimal import Decimal
from backend.worker.order_cache import LimitOrderCache
from backend.models import Order, OrderStatus, OrderSide, OrderType

@pytest.mark.asyncio
async def test_limit_order_cache_storage(mock_external_services):
    """
    Test storing and retrieving full order data in Redis Hash.
    """
    redis_client = mock_external_services["redis"]
    cache = LimitOrderCache(redis_client)
    
    order_id = uuid.uuid4()
    user_id = uuid.uuid4()
    ticker_id = "TEST-COIN"
    
    order = Order(
        id=order_id,
        user_id=user_id,
        ticker_id=ticker_id,
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
        quantity=Decimal("10.5"),
        unfilled_quantity=Decimal("10.5"),
        target_price=Decimal("100.0"),
        stop_price=None,
        trailing_gap=None,
        high_water_mark=None
    )
    
    # 1. Add Order
    await cache.add_order(order)
    
    # 2. Verify Data Retrieval
    data = await cache.get_order_data(str(order_id))
    assert data is not None
    assert data["id"] == str(order_id)
    assert data["user_id"] == str(user_id)
    assert data["ticker_id"] == ticker_id
    assert data["side"] == OrderSide.BUY.value
    assert data["type"] == OrderType.LIMIT.value
    assert data["quantity"] == "10.5"
    assert data["target_price"] == "100.0"
    
    # 3. Verify Index (Sorted Set)
    # Limit Buy -> oo:limit:TEST-COIN:buy
    candidates = await cache.fetch_candidates(ticker_id, OrderSide.BUY, 99.0, "LIMIT") # Price 99.0 < 100.0
    assert str(order_id) in candidates
    
    candidates_miss = await cache.fetch_candidates(ticker_id, OrderSide.BUY, 101.0, "LIMIT") # Price 101.0 > 100.0
    assert str(order_id) not in candidates_miss 
    # Wait. Logic check:
    # Limit Buy (Target 100). Current Price 99. Match? Yes (Buy cheap).
    # Redis Range [Current, +inf] ? No.
    # Limit Buy: "Buy at 100 or lower". 
    # Trigger: Current Price <= Target Price.
    # My fetch_candidates for LIMIT BUY returns `zrangebyscore(key, price, "+inf")`.
    # If I ask for price=99.0. Range [99.0, +inf]. 100.0 is in range. Match! Correct.
    
    # If I ask for price=101.0. Range [101.0, +inf]. 100.0 is NOT in range. No Match. Correct.

    # 4. Remove Order
    await cache.remove_order(str(order_id), ticker_id)
    
    data_after = await cache.get_order_data(str(order_id))
    assert data_after is None or data_after == {}
    
    candidates_after = await cache.fetch_candidates(ticker_id, OrderSide.BUY, 99.0, "LIMIT")
    assert str(order_id) not in candidates_after

@pytest.mark.asyncio
async def test_stop_order_cache_storage(mock_external_services):
    """
    Test storage for STOP orders.
    """
    redis_client = mock_external_services["redis"]
    cache = LimitOrderCache(redis_client)
    
    order_id = uuid.uuid4()
    ticker_id = "TEST-COIN"
    
    # Stop Loss Sell (Long Exit): Trigger if Price <= 90.
    order = Order(
        id=order_id,
        user_id=uuid.uuid4(),
        ticker_id=ticker_id,
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS,
        status=OrderStatus.PENDING,
        quantity=Decimal("5"),
        stop_price=Decimal("90.0")
    )
    
    await cache.add_order(order)
    
    # Verify Data
    data = await cache.get_order_data(str(order_id))
    assert data["stop_price"] == "90.0"
    
    # Verify Index
    # Stop Sell: Trigger if Price <= Stop.
    # fetch_candidates(STOP, SELL) returns range [price, +inf].
    # Current Price 95. Range [95, inf]. 90 is NOT in range. No trigger.
    # Current Price 85. Range [85, inf]. 90 IS in range. Trigger!
    
    candidates = await cache.fetch_candidates(ticker_id, OrderSide.SELL, 85.0, "STOP")
    assert str(order_id) in candidates
    
    candidates_no = await cache.fetch_candidates(ticker_id, OrderSide.SELL, 95.0, "STOP")
    assert str(order_id) not in candidates_no
