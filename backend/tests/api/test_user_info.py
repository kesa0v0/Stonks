import pytest
from httpx import AsyncClient
from backend.models import User
from backend.core.security import create_access_token
from backend.core.config import settings
from backend.core.deps import get_current_user # To import for unauthenticated test helper
from backend.app.main import app # To clear dependency overrides

@pytest.mark.asyncio
async def test_get_current_user_info(client: AsyncClient, test_user):
    """
    Test that an authenticated user can retrieve their own information via /login/me.
    """
    # 1. Login to get an access token for test_user
    login_data = {
        "username": "test@test.com",
        "password": "test1234"
    }
    response = await client.post("/api/v1/auth/login/access-token", data=login_data)
    assert response.status_code == 200
    access_token = response.json()["access_token"]

    # 2. Access /login/me with the access token
    headers = {"Authorization": f"Bearer {access_token}"}
    response = await client.get("/api/v1/auth/login/me", headers=headers)
    assert response.status_code == 200
    
    user_info = response.json()
    assert user_info["id"] == str(test_user)
    assert user_info["email"] == "test@test.com"
    assert user_info["nickname"] == "Tester"
    assert user_info["is_active"] is True

@pytest.mark.asyncio
async def test_get_current_user_info_unauthenticated(db_session, mock_external_services):
    """
    Test that an unauthenticated user cannot access /login/me and gets a 401.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.app.main import app
    from backend.core.deps import get_db, get_redis # Import necessary dependencies

    # Temporarily reset app dependency overrides for this test to ensure unauthenticated state
    app.dependency_overrides = {}
    
    # Re-apply only necessary overrides for the anonymous client
    async def override_get_db_for_unauth():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db_for_unauth

    async def override_get_redis_for_unauth():
        return mock_external_services["redis"]
    app.dependency_overrides[get_redis] = override_get_redis_for_unauth
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous_client:
        response = await anonymous_client.get("/api/v1/auth/login/me")
        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]
    
    # Clean up overrides after test
    app.dependency_overrides.clear()
