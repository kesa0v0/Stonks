from fastapi.testclient import TestClient

def test_login_access_token(client: TestClient, test_user):
    """
    Test standard login flow to get JWT token.
    """
    # 1. Try Login with correct credentials
    login_data = {
        "username": "test@test.com", # OAuth2 form expects 'username', we map it to email
        "password": "test1234"
    }
    
    # Note: Content-Type should be application/x-www-form-urlencoded, 
    # TestClient.post(data=...) handles this automatically.
    response = client.post("/login/access-token", data=login_data)
    
    assert response.status_code == 200, f"Login failed: {response.text}"
    tokens = response.json()
    assert "access_token" in tokens
    assert tokens["token_type"] == "bearer"

def test_login_wrong_password(client: TestClient, test_user):
    login_data = {
        "username": "test@test.com",
        "password": "wrongpassword"
    }
    response = client.post("/login/access-token", data=login_data)
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]
