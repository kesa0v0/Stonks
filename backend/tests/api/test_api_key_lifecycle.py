import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.core.database import get_db
from backend.core.cache import get_redis
from backend.core.config import settings

@pytest.mark.asyncio
async def test_api_key_lifecycle(db_session, test_user, mock_external_services):
    """
    Test full lifecycle of API Key: Create -> List -> Rotate -> Revoke -> Verify Usage
    """
    # Setup custom client without default get_current_user override
    # We need to re-apply get_db and get_redis overrides
    app.dependency_overrides = {}
    
    async def override_get_db():
        yield db_session
    
    async def override_get_redis():
        return mock_external_services["redis"]
        
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    
    # We need a client that can authenticate as test_user for management APIs (create/list/rotate/revoke)
    # So we'll generate a real token for test_user
    from backend.core.security import create_access_token
    token = create_access_token(subject=test_user)
    auth_headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create API Key
        response = await client.post("/api/v1/api-keys/", json={"name": "My Trading Bot"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "api_key" in data
        
        created_key = data["api_key"]
        key_id = data["key_id"]

        # 2. List API Keys
        response = await client.get("/api/v1/api-keys/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        item = next(i for i in data["items"] if i["id"] == key_id)
        assert item["name"] == "My Trading Bot"

        # 3. Use API Key to access protected endpoint
        # Access /market/price/{ticker_id} using ONLY X-API-Key (no Bearer token)
        api_key_headers = {"X-API-Key": created_key}
        
        response = await client.get("/api/v1/market/price/UNKNOWN", headers=api_key_headers)
        if response.status_code != 200:
            print(f"DEBUG: API Key Auth Failed. Status: {response.status_code}, Detail: {response.text}")
        assert response.status_code == 200 
        
        # 4. Rotate API Key
        response = await client.post(f"/api/v1/api-keys/{key_id}/rotate", headers=auth_headers)
        assert response.status_code == 200
        new_key = response.json()["api_key"]
        assert new_key != created_key
        
        # Verify old key fails
        headers_old = {"X-API-Key": created_key}
        response = await client.get("/api/v1/market/price/UNKNOWN", headers=headers_old)
        assert response.status_code == 401
        
        # Verify new key works
        headers_new = {"X-API-Key": new_key}
        response = await client.get("/api/v1/market/price/UNKNOWN", headers=headers_new)
        assert response.status_code == 200

        # 5. Revoke API Key
        response = await client.delete(f"/api/v1/api-keys/{key_id}", headers=auth_headers)
        assert response.status_code == 204
        
        # Verify new key fails after revoke
        response = await client.get("/api/v1/market/price/UNKNOWN", headers=headers_new)
        assert response.status_code == 401
        
    # Cleanup overrides
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_create_api_key_limit():
    pass
