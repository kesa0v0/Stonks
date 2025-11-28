import pytest
from httpx import AsyncClient
from backend.models import ApiKey
from sqlalchemy import select

@pytest.mark.asyncio
async def test_api_key_lifecycle(client: AsyncClient, db_session, test_user):
    """
    Test full lifecycle of API Key: Create -> List -> Rotate -> Revoke -> Verify Usage
    """
    # 1. Create API Key
    response = await client.post("/api-keys/", json={"name": "My Trading Bot"})
    assert response.status_code == 200
    data = response.json()
    assert "api_key" in data
    assert data["name"] == "My Trading Bot"
    
    created_key = data["api_key"]
    key_id = data["key_id"]

    # 2. List API Keys
    response = await client.get("/api-keys/")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) >= 1
    item = next(i for i in data["items"] if i["id"] == key_id)
    assert item["name"] == "My Trading Bot"
    assert item["key_prefix"] == created_key[:12]

    # 3. Use API Key to access protected endpoint
    # Using 'X-API-Key' header
    # We'll access /market/price/{ticker_id} which requires API Key
    # Note: We need a ticker. 'test_ticker' fixture is needed if we run this alone, 
    # but 'test_user' implies DB setup. Let's rely on mocking or simple endpoint.
    # Actually, /market/price/... uses get_current_user_by_api_key.
    
    # Use a mock ticker for the price check or reuse test_ticker logic if we add fixture
    # For simplicity, let's just check if auth passes (not 401/403).
    # But /market/price/UNKNOWN will return 200 with null price if auth works.
    
    headers = {"X-API-Key": created_key}
    # We need to clear the default Authorization header from client if it exists
    # But client fixture adds Authorization bearer token via dependency override?
    # No, client fixture in conftest adds dependency override for get_current_user.
    # But get_current_user_by_api_key is a DIFFERENT dependency.
    # So we need to ensure get_current_user_by_api_key works correctly with DB.
    
    response = await client.get("/market/price/UNKNOWN", headers=headers)
    # If key is valid, it should return 200 (with null price) or 404 depending on logic.
    # The code returns 200 with message if not found.
    assert response.status_code == 200 
    
    # 4. Rotate API Key
    response = await client.post(f"/api-keys/{key_id}/rotate")
    assert response.status_code == 200
    new_key = response.json()["api_key"]
    assert new_key != created_key
    
    # Verify old key fails
    headers_old = {"X-API-Key": created_key}
    response = await client.get("/market/price/UNKNOWN", headers=headers_old)
    assert response.status_code == 401
    
    # Verify new key works
    headers_new = {"X-API-Key": new_key}
    response = await client.get("/market/price/UNKNOWN", headers=headers_new)
    assert response.status_code == 200

    # 5. Revoke API Key
    response = await client.delete(f"/api-keys/{key_id}")
    assert response.status_code == 204
    
    # Verify new key fails after revoke
    response = await client.get("/market/price/UNKNOWN", headers=headers_new)
    assert response.status_code == 401
    assert "Invalid API Key" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_create_api_key_limit(client: AsyncClient, db_session, test_user):
        """
        (Optional) Test if there's a limit on number of keys (if implemented).
        Currently no limit is enforced in the code, but good to document.
        """
    pass
