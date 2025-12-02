import asyncio
import json
import logging
import redis.asyncio as async_redis
from backend.core.config import settings
from backend.core.discord import send_discord_webhook
from backend.services.common.config import get_whale_threshold_krw, get_message_template

logger = logging.getLogger(__name__)

async def _handle_trade_event(event: dict, redis: async_redis.Redis):
    try:
        if event.get("type") != "trade_executed":
            return
        qty = float(event.get("quantity") or 0)
        price = float(event.get("price") or 0)
        notional = abs(qty * price)
        try:
            threshold = await get_whale_threshold_krw(redis)
        except Exception:
            threshold = settings.WHALE_ALERT_THRESHOLD_KRW or 0
        if notional >= threshold:
            # 🐋 고래 알림 (템플릿)
            user = event.get("user_id")
            ticker = event.get("ticker_id")
            side = event.get("side")
            template = await get_message_template(redis, "whale_trade")
            msg = template.format(
                nickname=user,
                ticker=ticker,
                side=side,
                price=int(price),
                quantity=qty,
                notional=int(notional),
            )
            await send_discord_webhook(msg, human_channel=False)
    except Exception as e:
        logger.error(f"Error handling trade event: {e}")

async def _handle_liquidation_event(event: dict, redis: async_redis.Redis):
    try:
        if event.get("type") != "liquidation":
            return
        nickname = event.get("nickname") or event.get("user_id")
        ticker = event.get("ticker_id") or ""
        template = await get_message_template(redis, "liquidation")
        msg = template.format(
            nickname=nickname,
            ticker=ticker,
            equity=int(float(event.get("equity") or 0)),
            liability=int(float(event.get("liability") or 0)),
        )
        await send_discord_webhook(msg, human_channel=False)
    except Exception as e:
        logger.error(f"Error handling liquidation event: {e}")

async def _handle_human_event(event: dict, redis: async_redis.Redis):
    try:
        etype = event.get("type")
        if etype == "ipo_listed":
            symbol = event.get("symbol")
            rate = float(event.get("dividend_rate") or 0)
            template = await get_message_template(redis, "ipo_listed")
            msg = template.format(symbol=symbol, dividend_rate=rate, dividend_rate_pct=int(rate*100))
            await send_discord_webhook(msg, human_channel=True)
        elif etype == "dividend_paid":
            payer = event.get("payer_nickname")
            amount = int(float(event.get("total_dividend") or 0))
            template = await get_message_template(redis, "dividend_paid")
            msg = template.format(payer_nickname=payer, total_dividend=amount)
            await send_discord_webhook(msg, human_channel=True)
        elif etype == "bailout_processed":
            user = event.get("nickname")
            template = await get_message_template(redis, "bailout_processed")
            msg = template.format(nickname=user)
            await send_discord_webhook(msg, human_channel=True)
    except Exception as e:
        logger.error(f"Error handling human event: {e}")

async def notification_worker():
    redis = async_redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe("trade_events", "liquidation_events", "human_events")
    logger.info("NotificationWorker: Subscribed to trade/liquidation/human events…")
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                event = json.loads(message.get("data"))
            except Exception:
                continue
            channel = message.get("channel")
            if channel == "trade_events":
                await _handle_trade_event(event, redis)
            elif channel == "liquidation_events":
                await _handle_liquidation_event(event, redis)
            elif channel == "human_events":
                await _handle_human_event(event, redis)
    finally:
        await pubsub.close()
        await redis.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(notification_worker())
