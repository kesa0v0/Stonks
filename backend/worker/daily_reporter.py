import asyncio
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import redis.asyncio as async_redis
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import AsyncSessionLocal
from backend.core.discord import send_discord_webhook
from backend.services.common.config import get_message_template
from backend.models import Order, User

logger = logging.getLogger(__name__)

async def _compute_daily_stats(db: AsyncSession):
    # 기준: 최근 24시간 (UTC)
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=1)

    # 1) 일간 실현손익 집계
    stmt = select(Order.user_id, Order.realized_pnl).where(
        and_(Order.filled_at != None, Order.filled_at >= since)
    )
    result = await db.execute(stmt)

    pnl_map = defaultdict(float)
    for uid, pnl in result.all():
        if pnl is not None:
            pnl_map[uid] += float(pnl)

    # 2) 일간 거래 횟수 집계
    cnt_stmt = select(Order.user_id).where(and_(Order.created_at >= since))
    cnt_res = await db.execute(cnt_stmt)
    count_map = defaultdict(int)
    for (uid,) in cnt_res.all():
        count_map[uid] += 1

    # 유저 닉네임
    users_stmt = select(User.id, User.nickname)
    users = {row[0]: row[1] for row in (await db.execute(users_stmt)).all()}

    # Top gainer/loser (절대 실현손익 기준)
    top_gainer = None
    top_loser = None
    if pnl_map:
        top_gainer = max(pnl_map.items(), key=lambda x: x[1])
        top_loser = min(pnl_map.items(), key=lambda x: x[1])

    # Volume king
    volume_king = None
    if count_map:
        volume_king = max(count_map.items(), key=lambda x: x[1])

    return users, top_gainer, top_loser, volume_king

async def send_daily_report():
    async with AsyncSessionLocal() as db:
        users, g, l, v = await _compute_daily_stats(db)

    # 템플릿 기반 메시지 구성
    data = {
        "gainer_nickname": users.get(g[0], g[0]) if g else "-",
        "gainer_pnl": int(g[1]) if g else 0,
        "loser_nickname": users.get(l[0], l[0]) if l else "-",
        "loser_pnl": int(l[1]) if l else 0,
        "volume_king_nickname": users.get(v[0], v[0]) if v else "-",
        "trade_count": int(v[1]) if v else 0,
    }
    redis = async_redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)
    try:
        template = await get_message_template(redis, "daily_report")
    finally:
        await redis.aclose()
    msg = template.format(**data)
    await send_discord_webhook(msg, human_channel=False)

async def main():
    # 단일 실행 (스케줄러 없이도 실행 가능)
    await send_daily_report()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
