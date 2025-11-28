import pytest
from httpx import AsyncClient
from backend.models import User
from sqlalchemy import select
import uuid

# Note: Registration endpoint is not yet implemented in the provided code snippets.
# Based on `backend/app/routers/auth.py`, there is no `/register` or `/signup` endpoint.
# Access token login assumes user exists.
# If registration is missing, we should probably flag it or create a test that expects it to exist eventually.
# For now, let's assume there might be one or we skip this if it doesn't exist.

# Checking `backend/app/routers/auth.py` content again...
# It only has `login_access_token`, `refresh_token`, `logout`.
# There is NO registration endpoint.
# Users are created via `create_test_user.py` script or presumably a future admin API.

# So, I will create a test file but mark it as skipped or comment it out 
# until we implement registration, OR I will implement a simple test that checks 
# if we can prevent duplicate email if we were to add users manually (unit test style).

@pytest.mark.asyncio
async def test_prevent_duplicate_email(db_session):
    """
    Unit test: Ensure database constraints prevent duplicate emails.
    """
    # 1. Create first user
    user1 = User(
        id=uuid.uuid4(),
        email="duplicate@test.com",
        hashed_password="hash",
        nickname="User1",
        is_active=True
    )
    db_session.add(user1)
    await db_session.commit()
    
    # 2. Try to create second user with same email
    user2 = User(
        id=uuid.uuid4(),
        email="duplicate@test.com",
        hashed_password="hash",
        nickname="User2",
        is_active=True
    )
    db_session.add(user2)
    
    # 3. Expect IntegrityError
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        await db_session.commit()
    
    await db_session.rollback()
