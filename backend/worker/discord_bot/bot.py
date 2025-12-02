import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands

import redis.asyncio as async_redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import AsyncSessionLocal
from backend.models import Ticker, User
from backend.services.common.price import get_current_price
from backend.services.ranking_service import get_rankings_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

async def resolve_ticker_id(db: AsyncSession, query: str) -> Optional[str]:
    # 심볼 우선 조회, 없으면 이름 LIKE
    stmt = select(Ticker).where(Ticker.symbol.ilike(query.upper()))
    res = await db.execute(stmt)
    t = res.scalars().first()
    if t:
        return t.id
    stmt2 = select(Ticker).where(Ticker.name.ilike(f"%{query}%"))
    res2 = await db.execute(stmt2)
    t2 = res2.scalars().first()
    return t2.id if t2 else None

@tree.command(name="price", description="티커 현재가 조회 (/price btc)")
@app_commands.describe(ticker="티커 심볼 또는 이름")
async def price_command(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer(thinking=True)
    async with AsyncSessionLocal() as db:
        ticker_id = await resolve_ticker_id(db, ticker)
    if not ticker_id:
        await interaction.followup.send(f"티커 '{ticker}' 를 찾을 수 없어요.")
        return
    redis_client = async_redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)
    price = await get_current_price(redis_client, ticker_id)
    await redis_client.close()
    if price is None:
        await interaction.followup.send(f"{ticker_id} 현재가 데이터가 없어요.")
    else:
        await interaction.followup.send(f"{ticker_id} 현재가: {price} KRW")

@tree.command(name="rank", description="실시간 랭킹 TOP 5 (누적 PnL)")
async def rank_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    async with AsyncSessionLocal() as db:
        rankings = await get_rankings_data(db, ranking_type="pnl", limit=5)
    if not rankings:
        await interaction.followup.send("랭킹 데이터가 없어요.")
        return
    lines = ["🏆 실시간 랭킹 TOP 5 (누적 PnL)"]
    for r in rankings:
        lines.append(f"{r.rank}. {r.nickname} - {r.value}")
    await interaction.followup.send("\n".join(lines))

@tree.command(name="me", description="내 잔고/수익률 (DM 발송)")
async def me_command(interaction: discord.Interaction):
    # 계정 연동 필요 안내 (간단 메시지)
    await interaction.response.defer(thinking=True, ephemeral=True)
    await interaction.followup.send("디스코드 계정 연동이 필요합니다. 관리자에게 문의하세요.")

@client.event
async def on_ready():
    await tree.sync()
    logger.info(f"Logged in as {client.user}")

if __name__ == "__main__":
    token = settings.DISCORD_BOT_TOKEN
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN 이 설정되지 않았습니다.")
    client.run(token)
