import pytest
from httpx import AsyncClient
from sqlalchemy import select
from backend.models import User
from backend.core.security import get_password_hash
import uuid

@pytest.mark.asyncio
async def test_user_model_oauth_fields(db_session):
    """
    Test that the User model now correctly supports nullable hashed_password
    and includes provider and social_id fields.
    """
    # Create a user without a password (simulating an OAuth user)
    oauth_user_id = uuid.uuid4()
    oauth_user = User(
        id=oauth_user_id,
        email="oauth@example.com",
        hashed_password=None,  # This should now be allowed
        nickname="OAuthUser",
        is_active=True,
        provider="discord",
        social_id="1234567890"
    )
    db_session.add(oauth_user)
    await db_session.commit()

    # Retrieve the user and assert properties
    result = await db_session.execute(select(User).where(User.id == oauth_user_id))
    retrieved_user = result.scalars().first()

    assert retrieved_user is not None
    assert retrieved_user.email == "oauth@example.com"
    assert retrieved_user.hashed_password is None
    assert retrieved_user.nickname == "OAuthUser"
    assert retrieved_user.provider == "discord"
    assert retrieved_user.social_id == "1234567890"

@pytest.mark.asyncio
async def test_login_access_token_with_no_password_user(client: AsyncClient, db_session):
    """
    Test that a user without a hashed_password cannot log in via the password-based endpoint.
    """
    # Create a user with no password
    oauth_user_id = uuid.uuid4()
    oauth_user = User(
        id=oauth_user_id,
        email="no_pass@example.com",
        hashed_password=None,
        nickname="NoPassUser",
        is_active=True,
        provider="discord",
        social_id="0987654321"
    )
    db_session.add(oauth_user)
    await db_session.commit()

    login_data = {
        "username": "no_pass@example.com",
        "password": "anypassword"  # This password should not matter
    }

    response = await client.post("/login/access-token", data=login_data)
    
    # Expect a 401 Unauthorized because the user has no password for verification
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]

@pytest.mark.asyncio
async def test_login_access_token_with_local_user(client: AsyncClient, test_user):
    """
    Ensure existing password-based login still works for local users.
    (This test primarily relies on test_auth_api.py::test_login_access_token,
    but it's good to re-verify after model changes).
    """
    login_data = {
        "username": "test@test.com",
        "password": "test1234"
    }
    response = await client.post("/login/access-token", data=login_data)
    
    assert response.status_code == 200
    tokens = response.json()
    assert "access_token" in tokens
    assert tokens["token_type"] == "bearer"
    assert "refresh_token" in tokens
