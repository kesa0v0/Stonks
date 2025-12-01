import pytest
from httpx import AsyncClient
from decimal import Decimal
from backend.models import User, Wallet, Portfolio, Ticker, MarketType
from sqlalchemy import select
from backend.core.config import settings

@pytest.mark.asyncio
async def test_bankruptcy_flow(client: AsyncClient, db_session, test_user):
    # 1. Setup: Login and ensure initial state
    # Login
    login_data = {"username": "test@test.com", "password": "test1234"}
    response = await client.post("/api/v1/auth/login/access-token", data=login_data)
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Set initial money to a negative value (e.g., -50000) to allow bankruptcy
    stmt = select(Wallet).where(Wallet.user_id == test_user)
    wallet = (await db_session.execute(stmt)).scalars().first()
    if not wallet:
        wallet = Wallet(user_id=test_user, balance=Decimal("-50000"))
        db_session.add(wallet)
    else:
        wallet.balance = Decimal("-50000")
    await db_session.commit()

    # 2. File Bankruptcy
    response = await client.post("/api/v1/me/bankruptcy", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert float(data["balance"]) == -50000.0 # Balance should be initial negative value
    assert data["is_bankrupt"] is True
    assert data["human_stock_issued"] == 1000

    # 3. Verify DB State
    # User
    stmt = select(User).where(User.id == test_user)
    user = (await db_session.execute(stmt)).scalars().first()
    assert user.is_bankrupt is True
    assert user.bankruptcy_count == 1
    assert not user.nickname.startswith("[노예]") # Nickname should not change

    # Wallet
    await db_session.refresh(wallet)
    assert float(wallet.balance) == -50000.0 # Wallet balance should be initial negative value

    # Portfolio (Should have 1000 shares of HUMAN-{user_id})
    ticker_id = f"HUMAN-{test_user}"
    stmt = select(Portfolio).where(Portfolio.user_id == test_user, Portfolio.ticker_id == ticker_id)
    portfolio = (await db_session.execute(stmt)).scalars().first()
    assert portfolio is not None
    assert portfolio.quantity == 1000

    # Ticker
    stmt = select(Ticker).where(Ticker.id == ticker_id)
    ticker = (await db_session.execute(stmt)).scalars().first()
    assert ticker is not None
    assert ticker.market_type == MarketType.HUMAN

    # 4. Request Bailout (Safety Net)
    response = await client.post("/api/v1/human/bailout", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["message"] == "Bailout successful. System bought your shares."
    assert data["sold_quantity"] == 1000
    bailout_amount = data["bailout_amount"]
    assert bailout_amount > 0

    # 5. Verify Post-Bailout State
    # Portfolio should be empty (shares sold/burned)
    stmt = select(Portfolio).where(Portfolio.user_id == test_user, Portfolio.ticker_id == ticker_id)
    portfolio_after = (await db_session.execute(stmt)).scalars().first()
    assert portfolio_after is None

    # Wallet should have the money (initial negative + bailout amount)
    await db_session.refresh(wallet)
    assert float(wallet.balance) == float(Decimal("-50000") + Decimal(str(bailout_amount)))

@pytest.mark.asyncio
async def test_bankruptcy_flow_fail_if_positive_assets(client: AsyncClient, db_session, test_user):
    # Login
    login_data = {"username": "test@test.com", "password": "test1234"}
    response = await client.post("/api/v1/auth/login/access-token", data=login_data)
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Set initial money to a positive value (e.g., 10000)
    stmt = select(Wallet).where(Wallet.user_id == test_user)
    wallet = (await db_session.execute(stmt)).scalars().first()
    if not wallet:
        wallet = Wallet(user_id=test_user, balance=Decimal("10000"))
        db_session.add(wallet)
    else:
        wallet.balance = Decimal("10000")
    await db_session.commit()

    # Attempt to file bankruptcy
    response = await client.post("/api/v1/me/bankruptcy", headers=headers)
    assert response.status_code == 400
    assert "총 자산이 0 이하일 때만 파산 신청이 가능합니다." in response.json()["detail"]


@pytest.mark.asyncio
async def test_bailout_validation(client: AsyncClient, db_session, test_user):
    # Login
    login_data = {"username": "test@test.com", "password": "test1234"}
    response = await client.post("/api/v1/auth/login/access-token", data=login_data)
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Try bailout without being bankrupt
    # Reset user state first just in case
    stmt = select(User).where(User.id == test_user)
    user = (await db_session.execute(stmt)).scalars().first()
    user.is_bankrupt = False
    await db_session.commit()

    response = await client.post("/api/v1/human/bailout", headers=headers)
    assert response.status_code == 400
    assert "Only bankrupt users" in response.json()["detail"]

    # Verify bankrupt but no shares
    user.is_bankrupt = True
    await db_session.commit()
    
    # Ensure no shares
    stmt = select(Portfolio).where(Portfolio.user_id == test_user)
    portfolios = (await db_session.execute(stmt)).scalars().all()
    for p in portfolios:
        await db_session.delete(p)
    await db_session.commit()

    response = await client.post("/api/v1/human/bailout", headers=headers)
    assert response.status_code == 400
    assert "No shares found" in response.json()["detail"]
