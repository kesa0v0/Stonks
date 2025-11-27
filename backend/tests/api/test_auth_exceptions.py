import uuid
from sqlalchemy.orm import Session
from backend.models import User
from backend.core.security import get_password_hash
from fastapi.testclient import TestClient
from datetime import timedelta
from backend.core.security import create_access_token, create_refresh_token
from backend.core.deps import get_current_user

def test_expired_access_token(client: TestClient, test_user, mock_external_services):
    mock_redis = mock_external_services["redis"]
    mock_redis.exists.return_value = 0

    # 1. Create expired token
    token = create_access_token(subject=test_user, expires_delta=timedelta(minutes=-1))
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Disable override to test actual validation logic
    if get_current_user in client.app.dependency_overrides:
        del client.app.dependency_overrides[get_current_user]
        
    # Use any protected endpoint
    response = client.get("/orders", headers=headers)
    assert response.status_code == 401
    assert "Token has expired" in response.json()["detail"]

def test_tampered_access_token(client: TestClient, test_user, mock_external_services):
    mock_redis = mock_external_services["redis"]
    mock_redis.exists.return_value = 0

    token = create_access_token(subject=test_user)
    # Tamper the signature part
    tampered_token = token[:-1] + ("A" if token[-1] != "A" else "B")
    headers = {"Authorization": f"Bearer {tampered_token}"}
    
    if get_current_user in client.app.dependency_overrides:
        del client.app.dependency_overrides[get_current_user]
        
    response = client.get("/orders", headers=headers)
    assert response.status_code == 401
    assert "Could not validate credentials" in response.json()["detail"]

def test_expired_refresh_token(client: TestClient, test_user, mock_external_services):
    mock_redis = mock_external_services["redis"]
    mock_redis.exists.return_value = 0

    token = create_refresh_token(subject=test_user, expires_delta=timedelta(days=-1))
    refresh_data = {"refresh_token": token}
    
    # Refresh endpoint handles validation itself (no override issue)
    response = client.post("/login/refresh", json=refresh_data)
    assert response.status_code == 401
    assert "Refresh token has expired" in response.json()["detail"]

def test_tampered_refresh_token(client: TestClient, test_user, mock_external_services):
    mock_redis = mock_external_services["redis"]
    mock_redis.exists.return_value = 0

    token = create_refresh_token(subject=test_user)
    tampered_token = token + "junk"
    refresh_data = {"refresh_token": tampered_token}
    
    response = client.post("/login/refresh", json=refresh_data)
    assert response.status_code == 401
    assert "Invalid refresh token" in response.json()["detail"]

def test_login_inactive_user(client: TestClient, db_session: Session):
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
    db_session.commit()
    
    # 2. Try login
    login_data = {"username": "inactive@test.com", "password": "test1234"}
    response = client.post("/login/access-token", data=login_data)
    
    # 3. Assert
    assert response.status_code == 400
    assert "Inactive user" in response.json()["detail"]
