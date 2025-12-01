import httpx
from backend.core.config import settings
import asyncio

async def send_ntfy_notification(message: str, title: str = "Stonks Alert", priority: str = "default"):
    """
    ntfy를 통해 알림을 전송합니다.
    :param message: 알림 본문
    :param title: 알림 제목
    :param priority: 알림 우선순위 (max, high, default, low, min)
    """
    if not settings.NTFY_ENABLED or not settings.NTFY_TOPIC:
        return

    url = f"{settings.NTFY_URL}/{settings.NTFY_TOPIC}"
    headers = {
        "Title": title,
        "Priority": priority,
        "Tags": "warning" if priority in ["high", "max"] else "information_source"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, data=message.encode("utf-8"), headers=headers)
    except Exception as e:
        print(f"Failed to send ntfy notification: {e}")

def send_ntfy_sync(message: str, title: str = "Stonks Alert", priority: str = "default"):
    """
    동기적으로 ntfy 알림을 전송합니다 (예: 예외 핸들러 등 비동기 컨텍스트가 불확실한 경우).
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 이미 루프가 돌고 있다면 create_task로 던져둠 (fire and forget)
            loop.create_task(send_ntfy_notification(message, title, priority))
        else:
            loop.run_until_complete(send_ntfy_notification(message, title, priority))
    except RuntimeError:
        # 루프가 없으면 새로 만들어서 실행
        asyncio.run(send_ntfy_notification(message, title, priority))
