import asyncio
import uuid
import logging
from sqlalchemy import select
from backend.core.database import AsyncSessionLocal
from backend.models import User, Wallet
from backend.core.security import get_password_hash
from backend.core.config import settings
from decimal import Decimal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_admin_user():
    email = settings.ADMIN_EMAIL
    password = settings.ADMIN_PASSWORD
    nickname = "Admin"
    
    if not email or not password:
        logger.error("ADMIN_EMAIL or ADMIN_PASSWORD not set in settings.")
        return

    async with AsyncSessionLocal() as db:
        try:
            # Check if admin exists
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalars().first()
            
            if not user:
                logger.info(f"Creating admin user: {email}")
                hashed_pwd = get_password_hash(password)
                user = User(
                    id=uuid.uuid4(),
                    email=email,
                    hashed_password=hashed_pwd,
                    nickname=nickname,
                    is_superuser=True
                )
                db.add(user)
                
                # Admin wallet
                wallet = Wallet(user_id=user.id, balance=Decimal("0"))
                db.add(wallet)
                
                await db.commit()
                logger.info("✅ Admin user created successfully.")
            else:
                logger.info(f"Admin user {email} already exists. Updating password and ensuring superuser status.")
                user.hashed_password = get_password_hash(password)
                user.is_superuser = True
                await db.commit()
                logger.info("✅ Admin password updated.")
                
        except Exception as e:
            logger.error(f"Error creating admin user: {e}")
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(create_admin_user())
