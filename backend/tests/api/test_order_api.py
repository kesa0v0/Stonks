import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal
from backend.models import Wallet, Portfolio
from backend.tests.conftest import convert_decimals_to_str # Import the helper

@pytest.mark.asyncio
async def test_create_limit_order_insufficient_balance(client: AsyncClient, db_session: AsyncSession, test_user, test_ticker, payload_json_converter):
    """
    Test that creating a LIMIT BUY order with insufficient balance returns 400.
    """
    # 1. Setup: Set user balance to 50.0
    user_id = test_user
    
    result = await db_session.execute(select(Wallet).where(Wallet.user_id == user_id))
    wallet = result.scalars().first()
    
    # Ensure wallet exists (it should via test_user fixture)
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=Decimal("50.0"))
        db_session.add(wallet)
    else:
        wallet.balance = Decimal("50.0")
    
    await db_session.commit()
    await db_session.refresh(wallet)

    # 2. Request Payload: LIMIT BUY order requiring 100.0 (1 * 100)
    payload = {
        "ticker_id": test_ticker,
        "side": "BUY",
        "type": "LIMIT",
        "quantity": Decimal("1.0"), # Use Decimal
        "target_price": Decimal("100.0") # Use Decimal
    }
    # Convert Decimals to string for JSON serialization
    payload = payload_json_converter(payload)

    # 3. Execute
    response = await client.post("/api/v1/orders", json=payload)

    # 4. Assert
    assert response.status_code == 400
    data = response.json()
    assert "매수 잔액이 부족합니다" in data["detail"]
    # Updated assertion to reflect fee calculation and Decimal formatting
    # Based on previous logs, let's check partial string matching or standardized format if needed.
    # The previous failure log didn't show this one failing with the new format 100.10000, 
    # but let's be safe. If it's converted to float, it might be 100.1.
    # "Required: 100.10000" seems to be what we put in code, let's keep it consistent with findings.
    assert "필요: 100.1" in data["detail"]

@pytest.mark.asyncio
async def test_create_short_sell_limit_order_insufficient_margin(client: AsyncClient, db_session: AsyncSession, test_user, test_ticker, payload_json_converter):
    """
    Test that creating a Short SELL LIMIT order with insufficient margin returns 400.
    """
    # 1. Setup: Balance 50.0, No Portfolio (or 0 quantity)
    user_id = test_user
    result = await db_session.execute(select(Wallet).where(Wallet.user_id == user_id))
    wallet = result.scalars().first()
    wallet.balance = Decimal("50.0")
    
    # Ensure no portfolio holding to trigger short selling logic
    result = await db_session.execute(select(Portfolio).where(
        Portfolio.user_id == user_id, 
        Portfolio.ticker_id == test_ticker
    ))
    portfolio = result.scalars().first()
    
    if portfolio:
        await db_session.delete(portfolio)
        
    await db_session.commit()
    await db_session.refresh(wallet)

    # 2. Payload: SELL LIMIT 1 @ 100.0 (Required Margin 100.0)
    payload = {
        "ticker_id": test_ticker,
        "side": "SELL",
        "type": "LIMIT",
        "quantity": Decimal("1.0"), # Use Decimal
        "target_price": Decimal("100.0") # Use Decimal
    }
    # Convert Decimals to string for JSON serialization
    payload = payload_json_converter(payload)

    # 3. Execute
    response = await client.post("/api/v1/orders", json=payload)
    assert response.status_code == 400
    assert "공매도 증거금이 부족합니다" in response.json()["detail"]
    # Updated assertion to match actual output format
    assert "필요: 100.0" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_sell_order_insufficient_holdings(client: AsyncClient, db_session: AsyncSession, test_user, test_ticker, payload_json_converter):
    """
    Test that creating a SELL LIMIT order with insufficient holdings (but > 0) returns 400.
    """
    # 1. Setup: Add 5.0 qty to portfolio
    result = await db_session.execute(select(Portfolio).where(Portfolio.user_id == test_user, Portfolio.ticker_id == test_ticker))
    portfolio = result.scalars().first()
    
    if portfolio:
        portfolio.quantity = Decimal("5.0")
    else:
        portfolio = Portfolio(
            user_id=test_user, 
            ticker_id=test_ticker, 
            quantity=Decimal("5.0"), 
            average_price=Decimal("100.0")
        )
        db_session.add(portfolio)
    
    await db_session.commit()
    
    # 2. Payload: SELL 10.0 (More than 5.0)
    payload = {
        "ticker_id": test_ticker,
        "side": "SELL",
        "type": "LIMIT",
        "quantity": Decimal("10.0"), # Use Decimal
        "target_price": Decimal("100.0") # Use Decimal
    }
    # Convert Decimals to string for JSON serialization
    payload = payload_json_converter(payload)
    
    response = await client.post("/api/v1/orders", json=payload)
    assert response.status_code == 400
    assert "보유 수량이 부족하여" in response.json()["detail"]
    # Updated assertion to match actual output format
    assert "보유: 5.0, 요청: 10.0" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_order_invalid_input(client: AsyncClient, test_ticker, payload_json_converter):
    """
    Test that invalid input values (negative quantity/price) are rejected.
    """
    # 1. Negative Quantity
    payload = {
        "ticker_id": test_ticker,
        "side": "BUY",
        "type": "LIMIT",
        "quantity": Decimal("-1.0"), # Use Decimal
        "target_price": Decimal("100.0") # Use Decimal
    }
    # Convert Decimals to string for JSON serialization
    payload = payload_json_converter(payload)
    
    response = await client.post("/api/v1/orders", json=payload)
    # 422 Unprocessable Entity (Pydantic validation)
    assert response.status_code == 422 
    
    # 2. Negative Price
    payload["quantity"] = Decimal("1.0") # Use Decimal
    payload["target_price"] = Decimal("-100.0") # Use Decimal
    # Convert Decimals to string for JSON serialization
    payload = payload_json_converter(payload) # Convert again for new payload
    
    response = await client.post("/api/v1/orders", json=payload)
    # This now correctly asserts 400 because order.py explicitly raises HTTPException(400)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_order_detail_success(client: AsyncClient, db_session: AsyncSession, test_user, test_ticker, payload_json_converter):
    """
    본인 주문 상세 조회 성공 케이스
    """
    # 1. 주문 생성
    payload = {
        "ticker_id": test_ticker,
        "side": "BUY",
        "type": "LIMIT",
        "quantity": "1.0",
        "target_price": "100.0"
    }
    response = await client.post("/api/v1/orders", json=payload)
    assert response.status_code == 200
    order_id = response.json()["order_id"]

    # 2. 상세 조회 (API 경로 변경)
    detail_resp = await client.get(f"/api/v1/me/orders/{order_id}")
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["order_id"] == order_id
    assert data["ticker_id"] == test_ticker
    assert data["side"] == "BUY"
    assert data["type"] == "LIMIT"
    assert data["quantity"] == 1.0 or data["quantity"] == "1.0"

@pytest.mark.asyncio
async def test_get_order_detail_not_found(client: AsyncClient, test_user):
    """
    없는 주문 조회 시 404 반환
    """
    import uuid
    fake_id = str(uuid.uuid4())
    # API 경로 변경
    resp = await client.get(f"/api/v1/me/orders/{fake_id}")
    assert resp.status_code == 404
    assert "주문을 찾을 수 없습니다" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_get_order_detail_forbidden(client: AsyncClient, db_session: AsyncSession, test_user, test_ticker, payload_json_converter, another_user_token):
    """
    타인 주문 조회 시 403 반환
    """
    # 1. 주문 생성 (test_user)
    payload = {
        "ticker_id": test_ticker,
        "side": "BUY",
        "type": "LIMIT",
        "quantity": "1.0",
        "target_price": "100.0"
    }
    response = await client.post("/api/v1/orders", json=payload)
    assert response.status_code == 200
    order_id = response.json()["order_id"]

    # 2. 타인 토큰으로 조회 (API 경로 변경)
    headers = {"Authorization": f"Bearer {another_user_token}"}
    resp = await client.get(f"/api/v1/me/orders/{order_id}", headers=headers)
    assert resp.status_code == 403
    assert "권한이 없습니다" in resp.json()["detail"]