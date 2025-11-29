import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import User
from backend.core.security import get_password_hash
from httpx import AsyncClient
from datetime import timedelta
from backend.core.security import create_access_token, create_refresh_token
from backend.core.deps import get_current_user
from backend.tests.conftest import convert_decimals_to_str # Import the helper

@pytest.mark.asyncio
async def test_expired_access_token(client: AsyncClient, test_user, mock_external_services, payload_json_converter):
    mock_redis = mock_external_services["redis"]
    mock_redis.exists.return_value = 0

    # 1. Create expired token
    token = create_access_token(subject=test_user, expires_delta=timedelta(minutes=-1))
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Disable override to test actual validation logic
    from backend.app.main import app
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]
    
    try:
        # Use any protected endpoint (Changed from /orders to /me/orders)
        response = await client.get("/me/orders", headers=headers)
        assert response.status_code == 401
        assert "Token has expired" in response.json()["detail"]
    finally:
        pass

@pytest.mark.asyncio
async def test_tampered_access_token(client: AsyncClient, test_user, mock_external_services, payload_json_converter):
    mock_redis = mock_external_services["redis"]
    mock_redis.exists.return_value = 0

    token = create_access_token(subject=test_user)
    # Tamper the signature part
    tampered_token = token[:-1] + ("A" if token[-1] != "A" else "B")
    headers = {"Authorization": f"Bearer {tampered_token}"}
    
    from backend.app.main import app
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]
        
    try:
        # Changed from /orders to /me/orders
        response = await client.get("/me/orders", headers=headers)
        assert response.status_code == 401
        assert "Could not validate credentials" in response.json()["detail"]
    finally:
        pass

@pytest.mark.asyncio
async def test_expired_refresh_token(client: AsyncClient, test_user, mock_external_services, payload_json_converter):
    mock_redis = mock_external_services["redis"]
    mock_redis.exists.return_value = 0

    token = create_refresh_token(subject=test_user, expires_delta=timedelta(days=-1))
    refresh_data = {"refresh_token": token}
    
    # Refresh endpoint handles validation itself (no override issue)
    response = await client.post("/login/refresh", json=payload_json_converter(refresh_data)) # Convert payload
    assert response.status_code == 401
    assert "Refresh token has expired" in response.json()["detail"]

@pytest.mark.asyncio
async def test_tampered_refresh_token(client: AsyncClient, test_user, mock_external_services, payload_json_converter):
    mock_redis = mock_external_services["redis"]
    mock_redis.exists.return_value = 0

    token = create_refresh_token(subject=test_user)
    tampered_token = token + "junk"
    refresh_data = {"refresh_token": tampered_token}
    
    response = await client.post("/login/refresh", json=payload_json_converter(refresh_data)) # Convert payload
    assert response.status_code == 401
    assert "Invalid refresh token" in response.json()["detail"]

@pytest.mark.asyncio
async def test_login_inactive_user(client: AsyncClient, db_session: AsyncSession, payload_json_converter):
    # 1. Create inactive user
    user_id = uuid.uuid4()
    hashed = get_password_hash("test1234")
    user = User(
        id=user_id, 
        email="inactive@test.com", 
        hashed_password=hashed, 
        nickname="Inactive",
        is_active=False # Inactive
    )
    db_session.add(user)
    await db_session.commit()
    
    # 2. Try login
    login_data = {"username": "inactive@test.com", "password": "test1234"}
    # No need to convert login_data for login endpoints, as username/password are strings
    response = await client.post("/login/access-token", data=login_data)
    
    # 3. Assert
    assert response.status_code == 400
    assert "Inactive user" in response.json()["detail"]
