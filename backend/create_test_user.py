import uuid
from backend.core.database import SessionLocal
from backend.models import User
from backend.core.security import get_password_hash

db = SessionLocal()

TEST_USER_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

try:
    # 이미 있는지 확인
    user = db.query(User).filter(User.id == TEST_USER_ID).first()
    if not user:
        hashed_pwd = get_password_hash("test1234")
        user = User(
            id=uuid.UUID(TEST_USER_ID),
            email="test@kesa.uk",
            hashed_password=hashed_pwd,
            nickname="RichGuy"
        )
        db.add(user)
        db.commit()
        print(f"✅ Created test user: {TEST_USER_ID} with password 'test1234'")
    else:
        # 기존 유저 비밀번호 업데이트 (마이그레이션용)
        # 이미 해시된 비밀번호인지 확인하기 어려우므로, 강제로 업데이트하거나 dummy일때만 함.
        # 개발 편의를 위해 매번 실행 시 test1234로 초기화하는 것도 나쁘지 않음.
        user.hashed_password = get_password_hash("test1234")
        db.commit()
        print(f"✅ Updated test user: {TEST_USER_ID} password to 'test1234'")

except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()
