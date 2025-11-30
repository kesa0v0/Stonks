import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from backend.core.database import AsyncSessionLocal
from backend.services.season_service import end_current_season

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def scheduled_season_reset():
    """
    매월 1일 자정에 시즌을 초기화합니다.
    """
    logger.info("🔄 Starting Scheduled Season Reset...")
    async with AsyncSessionLocal() as db:
        try:
            new_season = await end_current_season(db)
            logger.info(f"✅ Season Reset Complete. New Season: {new_season.name}")
        except Exception as e:
            logger.error(f"❌ Season Reset Failed: {e}")

if __name__ == "__main__":
    scheduler = AsyncIOScheduler()
    
    # 매월 1일 00:00 실행
    # trigger = CronTrigger(day=1, hour=0, minute=0)
    
    # (테스트용) 매주 월요일 00:00 실행
    trigger = CronTrigger(day_of_week='mon', hour=0, minute=0)
    
    scheduler.add_job(scheduled_season_reset, trigger)
    
    logger.info("⏳ Season Manager Scheduler Started (Weekly Reset on Monday 00:00)")
    scheduler.start()
    
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
