import uuid
from backend.core.database import SessionLocal
from backend.models import User

db = SessionLocal()

TEST_USER_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

try:
    # 이미 있는지 확인
    user = db.query(User).filter(User.id == TEST_USER_ID).first()
    if not user:
        user = User(
            id=uuid.UUID(TEST_USER_ID),
            email="test@kesa.uk",
            hashed_password="dummy",
            nickname="RichGuy"
        )
        db.add(user)
        db.commit()
        print(f"✅ Created test user: {TEST_USER_ID}")
    else:
        print("ℹ️ Test user already exists")
except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()