import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from decimal import Decimal
from backend.models import Wallet, Portfolio

def test_create_limit_order_insufficient_balance(client: TestClient, db_session: Session, test_user, test_ticker):
    """
    Test that creating a LIMIT BUY order with insufficient balance returns 400.
    """
    # 1. Setup: Set user balance to 50.0
    user_id = test_user
    wallet = db_session.query(Wallet).filter(Wallet.user_id == user_id).first()
    # Ensure wallet exists (it should via test_user fixture)
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=Decimal("50.0"))
        db_session.add(wallet)
    else:
        wallet.balance = Decimal("50.0")
    
    db_session.commit()
    db_session.refresh(wallet)

    # 2. Request Payload: LIMIT BUY order requiring 100.0 (1 * 100)
    payload = {
        "ticker_id": test_ticker,
        "side": "BUY",
        "type": "LIMIT",
        "quantity": 1.0,
        "target_price": 100.0
    }

    # 3. Execute
    # Ensure the endpoint URL matches the router prefix. 
    # In router: router = APIRouter(prefix="/orders", ...)
    # In main.py (assumed): app.include_router(order.router)
    response = client.post("/orders", json=payload)

    # 4. Assert
    assert response.status_code == 400
    data = response.json()
    assert "Insufficient balance" in data["detail"]
    assert "Required: 100.0" in data["detail"]

def test_create_short_sell_limit_order_insufficient_margin(client: TestClient, db_session: Session, test_user, test_ticker):
    """
    Test that creating a Short SELL LIMIT order with insufficient margin returns 400.
    """
    # 1. Setup: Balance 50.0, No Portfolio (or 0 quantity)
    user_id = test_user
    wallet = db_session.query(Wallet).filter(Wallet.user_id == user_id).first()
    wallet.balance = Decimal("50.0")
    
    # Ensure no portfolio holding to trigger short selling logic
    portfolio = db_session.query(Portfolio).filter(
        Portfolio.user_id == user_id, 
        Portfolio.ticker_id == test_ticker
    ).first()
    if portfolio:
        db_session.delete(portfolio)
        
    db_session.commit()
    db_session.refresh(wallet)

    # 2. Payload: SELL LIMIT 1 @ 100.0 (Required Margin 100.0)
    payload = {
        "ticker_id": test_ticker,
        "side": "SELL",
        "type": "LIMIT",
        "quantity": 1.0,
        "target_price": 100.0
    }

    # 3. Execute
    response = client.post("/orders", json=payload)

    # 4. Assert
    assert response.status_code == 400
    data = response.json()
    assert "Insufficient balance for short selling" in data["detail"]
    assert "Required margin: 100.0" in data["detail"]
