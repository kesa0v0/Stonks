import pytest
from httpx import AsyncClient
from backend.core.deps import get_current_user
from backend.app.main import app # Import app to access dependency_overrides

@pytest.mark.asyncio
async def test_login_access_token(client: AsyncClient, test_user):
    """
    Test standard login flow to get JWT token.
    """
    # 1. Try Login with correct credentials
    login_data = {
        "username": "test@test.com", # OAuth2 form expects 'username', we map it to email
        "password": "test1234"
    }
    
    response = await client.post("/login/access-token", data=login_data)
    
    assert response.status_code == 200, f"Login failed: {response.text}"
    tokens = response.json()
    assert "access_token" in tokens
    assert tokens["token_type"] == "bearer"
    assert "refresh_token" in tokens

@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, test_user, mock_external_services):
    """
    Test refreshing the access token using a valid refresh token.
    """
    # Mock Redis to ensure token is not blacklisted
    mock_redis = mock_external_services["redis"]
    # Ensure exists returns 0 (not blacklisted)
    async def mock_exists_not_blacklisted(*keys):
        return 0
    mock_redis.exists.side_effect = mock_exists_not_blacklisted

    # 1. Login to get refresh token
    login_data = {
        "username": "test@test.com",
        "password": "test1234"
    }
    response = await client.post("/login/access-token", data=login_data)
    assert response.status_code == 200
    tokens = response.json()
    refresh_token = tokens["refresh_token"]
    
    # 2. Use refresh token
    refresh_data = {"refresh_token": refresh_token}
    response = await client.post("/login/refresh", json=refresh_data)
    
    assert response.status_code == 200
    new_tokens = response.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens

@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user):
    login_data = {
        "username": "test@test.com",
        "password": "wrongpassword"
    }
    response = await client.post("/login/access-token", data=login_data)
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]

@pytest.mark.asyncio
async def test_logout(client: AsyncClient, test_user, mock_external_services):
    """
    Test logout (blacklist) functionality.
    """
    # 1. Enable real auth logic by removing the override
    # We MUST remove the override because the default override (in conftest)
    # just returns the user from DB and skips Redis/Token validation.
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]

    # 2. Login
    login_data = {"username": "test@test.com", "password": "test1234"}
    response = await client.post("/login/access-token", data=login_data)
    assert response.status_code == 200
    token = response.json()["access_token"]
    
    # 3. Logout
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.post("/logout", headers=headers)
    assert response.status_code == 200
    
    # Verify Redis interaction
    mock_redis = mock_external_services["redis"]
    mock_redis.setex.assert_called() 
    
    # 4. Verify Access Denied (Redis should now have the token)
    # Changed from /orders to /me/orders
    response = await client.get("/me/orders", headers=headers)
    
    assert response.status_code == 401
    assert "Token has been revoked" in response.json()["detail"]


@pytest.mark.asyncio
async def test_logout_refresh_token(client: AsyncClient, test_user, mock_external_services):
    """
    Test that logout revokes the refresh token as well.
    """
    # 1. Login
    login_data = {"username": "test@test.com", "password": "test1234"}
    response = await client.post("/login/access-token", data=login_data)
    tokens = response.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    
    # 2. Logout with refresh token
    headers = {"Authorization": f"Bearer {access_token}"}
    logout_data = {"refresh_token": refresh_token}
    response = await client.post("/logout", headers=headers, json=logout_data)
    assert response.status_code == 200
    
    # 3. Try to refresh
    # Mock Redis exists to return 1 (Blacklisted)
    mock_redis = mock_external_services["redis"]
    
    # The refresh endpoint logic:
    # if await redis_client.exists(f"blacklist:{request.refresh_token}"):
    # It uses the redis_client injected via Depends(get_redis).
    # Since we mocked get_redis in conftest (via dependency_overrides),
    # this will use our In-Memory Mock Redis.
    # The logout logic already stored the key in redis_data.
    # So mock_exists will find it and return 1.
    
    refresh_data = {"refresh_token": refresh_token}
    response = await client.post("/login/refresh", json=refresh_data)
    
    assert response.status_code == 401
    assert "Refresh token has been revoked" in response.json()["detail"]