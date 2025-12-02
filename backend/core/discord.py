import httpx
from backend.core.config import settings

async def send_discord_webhook(message: str, human_channel: bool = False):
    """
    Discord 웹훅으로 메시지를 전송합니다.
    human_channel=True 이면 Human ETF 전용 채널에 전송.
    설정에 웹훅이 없으면 조용히 무시합니다.
    """
    url = settings.DISCORD_HUMAN_WEBHOOK_URL if human_channel else settings.DISCORD_ALERTS_WEBHOOK_URL
    if not url:
        return
    payload = {"content": message}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)
    except Exception as e:
        print(f"Failed to send Discord webhook: {e}")
