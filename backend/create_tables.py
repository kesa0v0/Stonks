# create_tables.py
import asyncio
from backend.core.database import engine
from backend.models import Base

async def init_db():
    print("Creating tables...")
    async with engine.begin() as conn:
        # run_sync를 통해 동기 함수인 create_all을 실행
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created successfully! 🎉")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(init_db())
