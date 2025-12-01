import asyncio
import uuid
from sqlalchemy import select
from backend.core.database import AsyncSessionLocal
from backend.models import User, Wallet
from backend.core.security import get_password_hash

async def create_test_user():
    TEST_USER_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    INITIAL_BALANCE = 100_000_000 # 1억원
    
    # 비동기 세션 생성
    async with AsyncSessionLocal() as db:
        try:
            # 이미 있는지 확인
            result = await db.execute(select(User).where(User.id == TEST_USER_ID))
            user = result.scalars().first()
            
            if not user:
                hashed_pwd = get_password_hash("test1234")
                user = User(
                    id=uuid.UUID(TEST_USER_ID),
                    email="test@kesa.uk",
                    hashed_password=hashed_pwd,
                    nickname="RichGuy"
                )
                db.add(user)
                
                # 지갑 생성
                wallet = Wallet(
                    user_id=user.id,
                    balance=INITIAL_BALANCE
                )
                db.add(wallet)
                
                await db.commit()
                print(f"✅ Created test user: {TEST_USER_ID} with password 'test1234' and balance {INITIAL_BALANCE}")
            else:
                # 기존 유저 비밀번호 업데이트
                user.hashed_password = get_password_hash("test1234")
                
                # 지갑 확인 및 잔고 충전
                w_result = await db.execute(select(Wallet).where(Wallet.user_id == user.id))
                wallet = w_result.scalars().first()
                if not wallet:
                    wallet = Wallet(user_id=user.id, balance=INITIAL_BALANCE)
                    db.add(wallet)
                    print(f"✅ Created missing wallet for test user with balance {INITIAL_BALANCE}")
                else:
                    wallet.balance = INITIAL_BALANCE
                    print(f"✅ Reset test user wallet balance to {INITIAL_BALANCE}")

                await db.commit()
                print(f"✅ Updated test user: {TEST_USER_ID} password to 'test1234'")
                
        except Exception as e:
            print(f"Error: {e}")
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(create_test_user())