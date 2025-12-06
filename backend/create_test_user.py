import asyncio
import uuid
import logging
from sqlalchemy import select
from backend.core.database import AsyncSessionLocal
from backend.models import User, Wallet
from backend.core.security import get_password_hash
from decimal import Decimal
from sqlalchemy import or_

logger = logging.getLogger(__name__)

async def create_test_user():
    USERS_TO_CREATE = [
        {
            "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", # 기존 TEST_USER_ID
            "email": "test@kesa.uk",
            "password": "test1234",
            "nickname": "RichGuy",
            "initial_balance": Decimal("100_000_000") # 1억원
        },
        {
            "id": str(uuid.uuid4()), # 새롭게 UUID 생성
            "email": "admin@stonks.com",
            "password": "admin",
            "nickname": "AdminUser",
            "initial_balance": Decimal("0") # 관리자는 초기 자금 필요 없을 수도 있음
        }
    ]
    
    # 비동기 세션 생성
    async with AsyncSessionLocal() as db:
        try:
            for user_data in USERS_TO_CREATE:
                user_id = user_data["id"]
                email = user_data["email"]
                password = user_data["password"]
                nickname = user_data["nickname"]
                initial_balance = user_data["initial_balance"]

                # UUID 또는 이메일 기준으로 기존 유저 확인
                result = await db.execute(
                    select(User).where(
                        or_(User.id == uuid.UUID(user_id), User.email == email)
                    )
                )
                user = result.scalars().first()

                if not user: # 유저가 없으면 새로 생성
                    hashed_pwd = get_password_hash(password)
                    user = User(
                        id=uuid.UUID(user_id),
                        email=email,
                        hashed_password=hashed_pwd,
                        nickname=nickname
                    )
                    db.add(user)

                    wallet = Wallet(user_id=user.id, balance=initial_balance)
                    db.add(wallet)

                    await db.commit()
                    logger.info(f"✅ Created user: {email} with password '{password}' and balance {initial_balance}")
                else: # 유저가 이미 있다면 비밀번호 및 지갑 업데이트
                    user.hashed_password = get_password_hash(password)
                    user.nickname = nickname
                    # 지갑 확인 및 잔고 충전/업데이트
                    w_result = await db.execute(select(Wallet).where(Wallet.user_id == user.id))
                    wallet = w_result.scalars().first()
                    if not wallet:
                        wallet = Wallet(user_id=user.id, balance=initial_balance)
                        db.add(wallet)
                        logger.info(f"✅ Created missing wallet for user {email} with balance {initial_balance}")
                    else:
                        wallet.balance = initial_balance # 기존 유저도 밸런스 초기화
                        logger.info(f"✅ Reset user {email} wallet balance to {initial_balance}")

                    await db.commit()
                    logger.info(f"✅ Updated user: {email} password to '{password}' and nickname to '{nickname}'")
                
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(create_test_user())