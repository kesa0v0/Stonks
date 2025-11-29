import pytest
import uuid
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import select
from backend.models import User, Wallet, Portfolio, Ticker, DividendHistory, MarketType, Currency
from backend.core.enums import OrderSide, OrderType
from backend.services.trade_service import execute_trade

@pytest.mark.asyncio
async def test_create_ipo(client: AsyncClient, db_session, test_user):
    """
    Test IPO creation.
    """
    # 1. Apply for IPO
    payload = {
        "quantity": 2000.0,
        "initial_price": 500.0,
        "dividend_rate": 0.1
    }
    response = await client.post("/human/ipo", json=payload)
    assert response.status_code == 200
    data = response.json()
    ticker_id = f"HUMAN-{test_user}"
    assert data["ticker_id"] == ticker_id
    
    # 2. Verify Ticker Created
    ticker_res = await db_session.execute(select(Ticker).where(Ticker.id == ticker_id))
    ticker = ticker_res.scalars().first()
    assert ticker is not None
    assert ticker.market_type == MarketType.HUMAN
    
    # 3. Verify Portfolio
    pf_res = await db_session.execute(select(Portfolio).where(Portfolio.user_id == test_user, Portfolio.ticker_id == ticker_id))
    portfolio = pf_res.scalars().first()
    assert portfolio is not None
    assert float(portfolio.quantity) == 2000.0
    assert float(portfolio.average_price) == 500.0
    
    # Verify User Dividend Rate
    user_res = await db_session.execute(select(User).where(User.id == test_user))
    user = user_res.scalars().first()
    assert float(user.dividend_rate) == 0.1
    
    # 4. Verify Duplicate IPO Failure
    response = await client.post("/human/ipo", json=payload)
    assert response.status_code == 400
    assert "already listed" in response.json()["detail"]

@pytest.mark.asyncio
async def test_bankrupt_ipo(client: AsyncClient, db_session):
    """
    Test IPO for a bankrupt user (Dividend rate constraint).
    """
    # 1. Create bankrupt user
    user_id = uuid.uuid4()
    user = User(id=user_id, email="bankrupt@t.com", hashed_password="pw", nickname="PoorGuy", is_active=True, is_bankrupt=True)
    wallet = Wallet(user_id=user_id, balance=0) 
    db_session.add(user)
    db_session.add(wallet)
    await db_session.commit()
    
    # 2. Login Mock
    from backend.core.deps import get_current_user_id
    from backend.app.main import app
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    
    try:
        # Case 1: Try low dividend rate (Should fail)
        payload_fail = {
            "quantity": 1000.0,
            "initial_price": 0.0,
            "dividend_rate": 0.1 # Less than 0.5
        }
        response = await client.post("/human/ipo", json=payload_fail)
        assert response.status_code == 400
        assert "dividend rate" in response.json()["detail"]
        
        # Case 2: Try valid dividend rate
        payload_ok = {
            "quantity": 1000.0,
            "initial_price": 0.0,
            "dividend_rate": 0.5
        }
        response = await client.post("/human/ipo", json=payload_ok)
        assert response.status_code == 200
        
        ticker_id = f"HUMAN-{user_id}"
        ticker_res = await db_session.execute(select(Ticker).where(Ticker.id == ticker_id))
        ticker = ticker_res.scalars().first()
        
        assert ticker.name == "PoorGuy's ETF"
        
    finally:
        del app.dependency_overrides[get_current_user_id]

@pytest.mark.asyncio
async def test_dividend_distribution(client: AsyncClient, db_session, mock_external_services):
    """
    Test dividend distribution when a Human ETF issuer makes profit.
    """
    redis_client = mock_external_services["redis"]
    
    # 1. Setup Users
    # Issuer (Slave)
    issuer = User(id=uuid.uuid4(), email="slave@t.com", hashed_password="pw", nickname="Slave", is_active=True, dividend_rate=Decimal("0.5"))
    issuer_wallet = Wallet(user_id=issuer.id, balance=Decimal("100000")) # Seed money
    
    # Shareholder (Master)
    shareholder = User(id=uuid.uuid4(), email="master@t.com", hashed_password="pw", nickname="Master", is_active=True)
    shareholder_wallet = Wallet(user_id=shareholder.id, balance=Decimal("0"))
    
    db_session.add_all([issuer, issuer_wallet, shareholder, shareholder_wallet])
    await db_session.commit()
    
    # 2. Setup Human ETF
    ticker_id = f"HUMAN-{issuer.id}"
    ticker = Ticker(id=ticker_id, symbol=f"HUMAN_{issuer.id}", name="Slave ETF", market_type=MarketType.HUMAN, currency=Currency.KRW, source="UPBIT", is_active=True)
    db_session.add(ticker)
    
    # Shareholder owns 500 shares (50% of assumed 1000 total)
    # Issuer owns remaining 500 (Self-owned shares don't get dividends in our logic)
    sh_portfolio = Portfolio(user_id=shareholder.id, ticker_id=ticker_id, quantity=Decimal("500"), average_price=10)
    iss_portfolio = Portfolio(user_id=issuer.id, ticker_id=ticker_id, quantity=Decimal("500"), average_price=0)
    db_session.add_all([sh_portfolio, iss_portfolio])
    await db_session.commit()
    
    # 3. Issuer makes profit on ANOTHER stock (e.g. BTC)
    # Setup BTC Ticker
    btc_id = "KRW-BTC"
    btc_ticker = Ticker(id=btc_id, symbol="BTC", name="Bitcoin", market_type=MarketType.CRYPTO, currency=Currency.KRW, source="UPBIT", is_active=True)
    # Use merge to avoid conflict if BTC exists from other tests
    await db_session.merge(btc_ticker)
    await db_session.commit()
    
    # Give issuer some BTC position
    # Buy: 1 BTC @ 1000
    issuer_btc_pf = Portfolio(user_id=issuer.id, ticker_id=btc_id, quantity=Decimal("1"), average_price=Decimal("1000"))
    db_session.add(issuer_btc_pf)
    await db_session.commit()
    
    # 4. Execute Sell (Profit)
    # Sell: 1 BTC @ 2000 -> PnL: 1000
    # Dividend: 1000 * 0.5 = 500
    # Shareholder Share: 500 shares / 500 shares (total circulation excluding self) = 100%?
    # Wait, total circulation calculation logic:
    # In dividend_service.py: total_shares = sum(s.quantity for s in shareholders) where user_id != payer_id
    # So total shares = 500 (only shareholder).
    # Shareholder ratio = 500 / 500 = 1.0 (100%)
    # So Shareholder gets full 500 KRW dividend.
    
    mock_external_services["redis_data"][f"price:{btc_id}"] = b'{"price": "2000.0"}'
    mock_external_services["redis_data"]["config:trading_fee_rate"] = b"0.0" # Zero fee for simple calc
    
    order_id = str(uuid.uuid4())
    success = await execute_trade(
        db=db_session,
        redis_client=redis_client,
        user_id=str(issuer.id),
        order_id=order_id,
        ticker_id=btc_id,
        side=OrderSide.SELL.value,
        quantity=1.0
    )
    assert success is True
    
    # 5. Verify Dividend Distribution
    await db_session.refresh(issuer_wallet)
    await db_session.refresh(shareholder_wallet)
    
    # Issuer:
    # Revenue: 2000
    # Dividend Paid: 500
    # Final Balance: 100000 (Initial) + 2000 (Revenue) - 500 (Dividend) = 101500
    assert float(issuer_wallet.balance) == 101500.0
    
    # Shareholder:
    # Dividend Received: 500
    assert float(shareholder_wallet.balance) == 500.0
    
    # 6. Verify History
    history_res = await db_session.execute(select(DividendHistory).where(DividendHistory.receiver_id == shareholder.id))
    history = history_res.scalars().first()
    assert history is not None
    assert float(history.amount) == 500.0
    assert history.ticker_id == ticker_id

@pytest.mark.asyncio
async def test_burn_shares(client: AsyncClient, db_session):
    """
    Test burning shares (Buyback & Burn).
    """
    # 1. Create bankrupt user
    user_id = uuid.uuid4()
    user = User(id=user_id, email="burn@t.com", hashed_password="pw", nickname="Burner", is_active=True, is_bankrupt=True)
    wallet = Wallet(user_id=user_id, balance=0)
    db_session.add(user)
    db_session.add(wallet)
    await db_session.commit()
    
    # Login Mock
    from backend.core.deps import get_current_user_id
    from backend.app.main import app
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    
    try:
        # 2. IPO (1000 shares)
        ipo_payload = {"quantity": 1000.0, "initial_price": 0.0, "dividend_rate": 0.5}
        await client.post("/human/ipo", json=ipo_payload)
        
        # 3. Partial Burn (500 shares)
        burn_payload = {"quantity": 500.0}
        response = await client.post("/human/burn", json=burn_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["is_delisted"] is False
        assert float(data["remaining_shares"]) == 500.0
        
        await db_session.refresh(user)
        assert user.is_bankrupt is True # Still bankrupt
        
        # 4. Full Burn (Remaining 500 shares)
        response = await client.post("/human/burn", json=burn_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["is_delisted"] is True
        assert float(data["remaining_shares"]) == 0.0
        
        # 5. Verify Freedom
        await db_session.refresh(user)
        assert user.is_bankrupt is False # Freed!
        
        ticker_res = await db_session.execute(select(Ticker).where(Ticker.id == f"HUMAN-{user_id}"))
        ticker = ticker_res.scalars().first()
        assert ticker.is_active is False # Delisted
        
    finally:
        del app.dependency_overrides[get_current_user_id]