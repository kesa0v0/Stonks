import pytest
from httpx import AsyncClient
from backend.models import Watchlist
from sqlalchemy import select

@pytest.mark.asyncio
async def test_watchlist_lifecycle(client: AsyncClient, test_user, test_ticker, db_session):
    """
    Test the full lifecycle of a watchlist item: Add -> Get -> Duplicate -> Remove -> Remove Again
    """
    # 1. Login
    login_data = {"username": "test@test.com", "password": "test1234"}
    response = await client.post("/api/v1/auth/login/access-token", data=login_data)
    access_token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    
    ticker_id = test_ticker

    # 2. Add to watchlist
    response = await client.post(f"/api/v1/me/watchlist/{ticker_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Ticker added to watchlist"

    # Verify DB
    stmt = select(Watchlist).where(Watchlist.user_id == test_user, Watchlist.ticker_id == ticker_id)
    watchlist_item = (await db_session.execute(stmt)).scalars().first()
    assert watchlist_item is not None

    # 3. Get watchlist
    response = await client.get("/api/v1/me/watchlist", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticker"]["id"] == ticker_id
    # Price might be 0.0 or mocked value depending on redis mock
    # mocking redis in conftest returns 100.0 for "price:..." keys usually?
    # check conftest: if key starts with "price:", returns 100.0.
    # But get_current_price uses constant.REDIS_PREFIX_PRICE. 
    # I should check constants.REDIS_PREFIX_PRICE value.
    
    # 4. Add duplicate (should fail)
    response = await client.post(f"/api/v1/me/watchlist/{ticker_id}", headers=headers)
    assert response.status_code == 400
    assert "already in watchlist" in response.json()["detail"]

    # 5. Remove from watchlist
    response = await client.delete(f"/api/v1/me/watchlist/{ticker_id}", headers=headers)
    assert response.status_code == 200
    
    # Verify DB
    watchlist_item = (await db_session.execute(stmt)).scalars().first()
    assert watchlist_item is None

    # 6. Remove again (should fail)
    response = await client.delete(f"/api/v1/me/watchlist/{ticker_id}", headers=headers)
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_add_invalid_ticker_to_watchlist(client: AsyncClient, test_user, db_session):
    # Login
    login_data = {"username": "test@test.com", "password": "test1234"}
    response = await client.post("/api/v1/auth/login/access-token", data=login_data)
    access_token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # Add non-existent ticker
    response = await client.post("/api/v1/me/watchlist/INVALID-TICKER", headers=headers)
    # Should fail with 404 or 500 depending on FK constraint handling in SQLite/PG
    # The service catches IntegrityError and maps to 404.
    # SQLite enforces FKs usually? Yes in modern versions/drivers if configured.
    # If not enforced, it might succeed (which is bad but depends on DB).
    # Let's assert 404.
    assert response.status_code == 404
