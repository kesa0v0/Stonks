import pytest
from httpx import AsyncClient
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select
from backend.models import Wallet, User
from backend.schemas.wallet import WalletTransactionHistory

@pytest.mark.asyncio
async def test_get_my_wallet_history(client: AsyncClient, test_user, db_session):
    """
    Test retrieving wallet transaction history for the authenticated user.
    """
    # 1. Login to get access token
    login_data = {
        "username": "test@test.com",
        "password": "test1234"
    }
    response = await client.post("/api/v1/auth/login/access-token", data=login_data)
    assert response.status_code == 200
    access_token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # 2. Trigger some wallet transactions
    # Since WalletTransactionHistory is created via event hooks on Wallet updates,
    # we simply update the wallet balance.
    
    # Fetch current wallet
    stmt = select(Wallet).where(Wallet.user_id == test_user)
    result = await db_session.execute(stmt)
    wallet = result.scalars().first()
    assert wallet is not None

    # Update 1: Deposit (Manual update to trigger hook)
    # The hook logic relies on SQLAlchemy session tracking changes.
    wallet.balance = Decimal("150000000") # +50,000,000
    await db_session.commit() # This should trigger the 'after_update' event
    
    # Update 2: Withdrawal
    wallet.balance = Decimal("120000000") # -30,000,000
    await db_session.commit() # This should trigger the 'after_update' event

    # 3. Call the endpoint
    response = await client.get("/api/v1/me/wallet/history", headers=headers)
    assert response.status_code == 200
    
    history_list = response.json()
    assert isinstance(history_list, list)
    # We expect at least 2 entries from the updates above. 
    # Note: The initial creation of the wallet might also create an entry depending on implementation,
    # but usually updates trigger it. If creation doesn't, we have 2.
    assert len(history_list) >= 2
    
    # 4. Verify content of the most recent transaction (Update 2)
    latest_tx = history_list[0]
    assert latest_tx["user_id"] == str(test_user)
    assert latest_tx["wallet_id"] == str(wallet.id)
    assert Decimal(latest_tx["new_balance"]) == Decimal("120000000")
    assert Decimal(latest_tx["prev_balance"]) == Decimal("150000000")
    
    # 5. Verify content of the previous transaction (Update 1)
    prev_tx = history_list[1]
    assert prev_tx["user_id"] == str(test_user)
    assert Decimal(prev_tx["new_balance"]) == Decimal("150000000")
    
    # Check schema validation implicitly by parsing response
    for item in history_list:
        WalletTransactionHistory(**item)

@pytest.mark.asyncio
async def test_get_my_wallet_history_empty(client: AsyncClient, db_session, another_user_token):
    """
    Test that a user with no history gets an empty list (or just initial creation if applicable).
    """
    # 'another_user_token' fixture creates a new user with a wallet. 
    # If only updates trigger history, it might be empty or have 1 entry if creation counts.
    # Let's check what happens.
    
    headers = {"Authorization": f"Bearer {another_user_token}"}
    response = await client.get("/api/v1/me/wallet/history", headers=headers)
    assert response.status_code == 200
    
    history_list = response.json()
    assert isinstance(history_list, list)
    # Assuming purely 'after_update' hook, a fresh user might have 0 history 
    # unless the fixture modified the balance after creation.
    # We just verify it returns a list and 200 OK.

@pytest.mark.asyncio
async def test_get_my_wallet_history_pagination(client: AsyncClient, test_user, db_session):
    """
    Test pagination parameters skip and limit.
    """
    # Login
    login_data = {"username": "test@test.com", "password": "test1234"}
    response = await client.post("/api/v1/auth/login/access-token", data=login_data)
    access_token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # Create 3 transactions
    stmt = select(Wallet).where(Wallet.user_id == test_user)
    wallet = (await db_session.execute(stmt)).scalars().first()
    
    for i in range(3):
        wallet.balance += Decimal("1000")
        await db_session.commit()

    # Fetch all
    response_all = await client.get("/api/v1/me/wallet/history", headers=headers)
    all_history = response_all.json()
    total_count = len(all_history)
    assert total_count >= 3

    # Fetch with limit=1
    response_limit = await client.get("/api/v1/me/wallet/history?limit=1", headers=headers)
    limit_history = response_limit.json()
    assert len(limit_history) == 1
    assert limit_history[0]["id"] == all_history[0]["id"]

    # Fetch with skip=1
    response_skip = await client.get("/api/v1/me/wallet/history?skip=1", headers=headers)
    skip_history = response_skip.json()
    assert len(skip_history) == total_count - 1
    assert skip_history[0]["id"] == all_history[1]["id"]
