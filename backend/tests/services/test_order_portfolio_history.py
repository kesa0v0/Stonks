import pytest
import json
from uuid import UUID
from sqlalchemy import select
from decimal import Decimal
from unittest.mock import AsyncMock, patch
import uuid # Added import

from backend.models import Order, OrderStatus, Portfolio, OrderStatusHistory, PortfolioHistory, Wallet, Ticker # Added Wallet, Ticker
from backend.core.enums import OrderType, OrderSide
from backend.services.order_service import place_order, cancel_order_logic
from backend.services.trade_service import execute_trade # Added import
from backend.core.audit import publish_audit_log # Import the function to mock

@pytest.mark.asyncio
async def test_order_status_history_on_insert_and_cancel(db_session, test_user, test_ticker, mock_external_services):
    user_id = UUID(str(test_user))

    # Mock the audit publisher
    with patch("backend.services.order_service.publish_audit_log", new=AsyncMock()) as mock_publish_audit_log:
        # Place a LIMIT order (goes to DB as PENDING)
        from backend.schemas.order import OrderCreate
        order_in = OrderCreate(
            ticker_id=test_ticker,
            side=OrderSide.BUY,
            quantity=Decimal("1.0"),
            type=OrderType.LIMIT,
            target_price=Decimal("10.0"),
        )

        res = await place_order(db_session, mock_external_services["redis"], user_id, order_in)
        order_id = UUID(res["order_id"])

        # Verify audit log for insert
        mock_publish_audit_log.assert_called()
        # Find the call for order_status_history and PENDING status
        pending_log = None
        for call_args, call_kwargs in mock_publish_audit_log.call_args_list:
            if call_args[0] == "order_status_history" and call_args[1].get("new_status") == str(OrderStatus.PENDING):
                pending_log = call_args[1]
                break
        assert pending_log is not None
        assert UUID(pending_log["order_id"]) == order_id
        assert UUID(pending_log["user_id"]) == user_id
        assert pending_log["prev_status"] is None

        # Reset mock for next action
        mock_publish_audit_log.reset_mock()

        # Cancel the order -> status should become CANCELLED and history recorded
        await cancel_order_logic(db_session, mock_external_services["redis"], user_id, order_id)
        
        # Verify audit log for cancel
        mock_publish_audit_log.assert_called()
        cancelled_log = None
        for call_args, call_kwargs in mock_publish_audit_log.call_args_list:
            if call_args[0] == "order_status_history" and call_args[1].get("new_status") == str(OrderStatus.CANCELLED):
                cancelled_log = call_args[1]
                break
        assert cancelled_log is not None
        assert UUID(cancelled_log["order_id"]) == order_id
        assert UUID(cancelled_log["user_id"]) == user_id
        assert cancelled_log["prev_status"] == str(OrderStatus.PENDING)

@pytest.mark.asyncio
async def test_portfolio_history_via_execute_trade(db_session, test_user, test_ticker, mock_external_services):
    user_id = UUID(str(test_user))
    redis_client = mock_external_services["redis"]

    # Mock publish_audit_log
    with patch("backend.services.trade_service.publish_audit_log", new=AsyncMock()) as mock_publish_audit_log:
        # Setup initial wallet and ticker (ensure they exist or create if not)
        existing_wallet = await db_session.execute(select(Wallet).where(Wallet.user_id == user_id))
        wallet = existing_wallet.scalars().first()
        if not wallet:
            wallet = Wallet(user_id=user_id, balance=Decimal("100000.0"))
            db_session.add(wallet)
        else:
            wallet.balance = Decimal("100000.0") # Ensure sufficient balance

        existing_ticker = await db_session.execute(select(Ticker).where(Ticker.id == test_ticker))
        ticker = existing_ticker.scalars().first()
        if not ticker:
            ticker = Ticker(id=test_ticker, symbol="TEST", name="Test Coin", market_type="CRYPTO", currency="KRW", is_active=True)
            db_session.add(ticker)
        
        await db_session.commit()
        await db_session.refresh(wallet)
        await db_session.refresh(ticker)
        # Mock current price (needed by execute_trade)
        mock_external_services["redis_data"][f"price:{test_ticker}"] = b'{"price": "100.0"}'

        # --- Initial Trade (Insert/Update portfolio) ---
        order_id_1 = str(uuid.uuid4())
        # Call execute_trade which should lead to portfolio changes
        success, _ = await execute_trade(
            db=db_session,
            redis_client=redis_client,
            user_id=str(user_id),
            order_id=order_id_1,
            ticker_id=test_ticker,
            side=OrderSide.BUY.value,
            quantity=1.0
        )
        assert success is True                    # Verify initial portfolio history audit log (buy 1 at 100)        # It's an "update" from empty to 1.0 quantity        initial_log = None
        for call_args, call_kwargs in mock_publish_audit_log.call_args_list:
            if call_args[0] == "portfolio_history":
                log_data = call_args[1]
                if UUID(log_data["user_id"]) == user_id and log_data["ticker_id"] == test_ticker:
                    initial_log = log_data
                    break
        assert initial_log is not None
        assert initial_log["action"] == "update"
        assert Decimal(initial_log["new_quantity"]) == Decimal("1.0")
        assert float(initial_log["new_average_price"]) == pytest.approx(100.1, rel=1e-8) # 100 + fee (0.1%)

        # --- Update (another trade) ---
        mock_publish_audit_log.reset_mock()
        order_id_2 = str(uuid.uuid4())
        success, _ = await execute_trade(
            db=db_session,
            redis_client=redis_client,
            user_id=str(user_id),
            order_id=order_id_2,
            ticker_id=test_ticker,
            side=OrderSide.BUY.value,
            quantity=1.0
        )
        assert success is True
        
        # Verify update portfolio history audit log (buy another 1 at 100)
        updated_log = None
        for call_args, call_kwargs in mock_publish_audit_log.call_args_list:
            if call_args[0] == "portfolio_history":
                log_data = call_args[1]
                if UUID(log_data["user_id"]) == user_id and log_data["ticker_id"] == test_ticker:
                    updated_log = log_data
                    break
        assert updated_log is not None
        assert updated_log["action"] == "update"
        assert Decimal(updated_log["prev_quantity"]) == Decimal("1.0")
        assert Decimal(updated_log["new_quantity"]) == Decimal("2.0")
        
        # --- Delete (sell all) ---
        mock_publish_audit_log.reset_mock()
        order_id_3 = str(uuid.uuid4())
        mock_external_services["redis_data"][f"price:{test_ticker}"] = b'{"price": "100.0"}'
        # Ensure user has enough shares to sell
        portfolio_item = await db_session.execute(select(Portfolio).where(Portfolio.user_id == user_id, Portfolio.ticker_id == test_ticker))
        portfolio_item = portfolio_item.scalars().first()
        portfolio_item.quantity = Decimal("2.0") # Ensure quantity is correct for sell
        await db_session.commit()


        success, _ = await execute_trade(
            db=db_session,
            redis_client=redis_client,
            user_id=str(user_id),
            order_id=order_id_3,
            ticker_id=test_ticker,
            side=OrderSide.SELL.value,
            quantity=2.0
        )
        assert success is True
        
        # Verify delete portfolio history audit log (sell all to 0)
        deleted_log = None
        for call_args, call_kwargs in mock_publish_audit_log.call_args_list:
            if call_args[0] == "portfolio_history":
                log_data = call_args[1]
                if UUID(log_data["user_id"]) == user_id and log_data["ticker_id"] == test_ticker:
                    deleted_log = log_data
                    break
        assert deleted_log is not None
        assert deleted_log["action"] == "update" # trade_service logs "update" even for delete, but new_quantity becomes 0
        assert Decimal(deleted_log["new_quantity"]) == Decimal("0.0")
