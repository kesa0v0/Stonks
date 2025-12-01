import pytest
from httpx import AsyncClient
from backend.core.config import settings

@pytest.mark.asyncio
async def test_admin_get_fee(client: AsyncClient, admin_user_token):
    """
    Test that an admin user can get the trading fee.
    """
    headers = {"Authorization": f"Bearer {admin_user_token}"}
    response = await client.get("/api/v1/admin/fee", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "fee_rate" in data
    # Default fee rate from settings or Redis mock should be 0.001
    assert data["fee_rate"] == 0.001

@pytest.mark.asyncio
async def test_admin_update_fee(client: AsyncClient, admin_user_token, mock_external_services):
    """
    Test that an admin user can update the trading fee.
    """
    headers = {"Authorization": f"Bearer {admin_user_token}"}
    new_fee_rate = 0.0025
    response = await client.put("/api/v1/admin/fee", headers=headers, json={"fee_rate": new_fee_rate})
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Trading fee rate updated successfully"
    assert float(data["fee_rate"]) == new_fee_rate

    # Verify the update by getting the fee again
    response = await client.get("/api/v1/admin/fee", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert float(data["fee_rate"]) == new_fee_rate

    # Verify directly from Redis mock
    mock_redis = mock_external_services["redis"]
    stored_fee = await mock_redis.get("config:trading_fee_rate")
    assert float(stored_fee) == new_fee_rate

@pytest.mark.asyncio
async def test_admin_access_forbidden_for_regular_user(client: AsyncClient, another_user_token):
    """
    Test that a regular user cannot access admin endpoints.
    """
    headers = {"Authorization": f"Bearer {another_user_token}"}
    response = await client.get("/api/v1/admin/fee", headers=headers)
    assert response.status_code == 403
    assert "The user doesn't have enough privileges" in response.json()["detail"]

@pytest.mark.asyncio
async def test_admin_access_unauthenticated(db_session, mock_external_services):
    """
    Test that an unauthenticated user cannot access admin endpoints.
    A new client is created without any default authentication headers.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.app.main import app
    from backend.core.deps import get_db, get_current_user, get_redis # Import necessary dependencies

    # Temporarily override dependencies to ensure no user is authenticated by default
    # For a truly unauthenticated test, we need to ensure get_current_user is not
    # providing a user. The client fixture in conftest.py injects a user.
    # So, we create a new client and manually set overrides or ensure they are cleared.
    
    # We will temporarily override get_db and get_redis for this client
    # and ensure get_current_user returns None or raises 401.
    
    # Let's ensure the app's default get_current_user is used, which should handle 401 if no token.
    # No, the client fixture already overrides get_current_user to return test_user.
    # The best way is to create a client that does NOT use the default overrides.
    
    # Reset app overrides for this specific test
    app.dependency_overrides = {}
    
    # Re-apply only necessary overrides
    async def override_get_db_for_unauth():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db_for_unauth

    async def override_get_redis_for_unauth():
        return mock_external_services["redis"]
    app.dependency_overrides[get_redis] = override_get_redis_for_unauth
    
    # Crucially, ensure get_current_user isn't overridden to provide a user
    # Or, mock it to raise 401 if called without token.
    # For this specific scenario, we're not sending a token, so the original get_current_user should
    # throw 401.
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous_client:
        response = await anonymous_client.get("/api/v1/admin/fee")
        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"] # Expect JWT validation failure
        
        # Clean up overrides after test
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_admin_update_fee_invalid_value(client: AsyncClient, admin_user_token):
    """
    Test that updating fee with invalid values (e.g., out of range) fails.
    """
    headers = {"Authorization": f"Bearer {admin_user_token}"}
    
    # Too low
    response = await client.put("/api/v1/admin/fee", headers=headers, json={"fee_rate": -0.01})
    assert response.status_code == 422 # Unprocessable Entity
    
    # Too high
    response = await client.put("/api/v1/admin/fee", headers=headers, json={"fee_rate": 1.1})
    assert response.status_code == 422 # Unprocessable Entity
