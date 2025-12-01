import pytest
from httpx import AsyncClient
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
from unittest.mock import patch

@pytest.mark.asyncio
async def test_market_status_krx_open(client: AsyncClient):
    """
    Test KRX Open: Monday 10:00 AM KST (Sunday 9:00 PM EST - US Closed)
    """
    # 2025-06-02 (Mon) 10:00:00 KST
    # UTC: 2025-06-02 01:00:00
    kst = ZoneInfo("Asia/Seoul")
    mock_now = datetime(2025, 6, 2, 10, 0, 0, tzinfo=kst).astimezone(timezone.utc)
    
    with patch("backend.services.market_service.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = datetime # 다른 메서드는 그대로 동작하게
        
        response = await client.get("/api/v1/market/status")
        assert response.status_code == 200
        data = response.json()
        
        assert data["krx"] == "OPEN"
        assert data["us"] == "CLOSED" # US 21:00 (Sunday)
        assert data["crypto"] == "OPEN"

@pytest.mark.asyncio
async def test_market_status_us_open(client: AsyncClient):
    """
    Test US Open: Monday 11:00 AM EST (Tuesday 00:00 AM KST - KRX Closed)
    """
    # 2025-06-02 (Mon) 11:00:00 New_York
    # UTC: 2025-06-02 15:00:00
    ny = ZoneInfo("America/New_York")
    mock_now = datetime(2025, 6, 2, 11, 0, 0, tzinfo=ny).astimezone(timezone.utc)
    
    with patch("backend.services.market_service.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = datetime
        
        response = await client.get("/api/v1/market/status")
        assert response.status_code == 200
        data = response.json()
        
        assert data["us"] == "OPEN"
        assert data["krx"] == "CLOSED" # KRX 00:00 (Tue)
        assert data["crypto"] == "OPEN"

@pytest.mark.asyncio
async def test_market_status_weekend(client: AsyncClient):
    """
    Test Weekend: Saturday
    """
    # 2025-06-07 (Sat) 12:00:00 KST
    kst = ZoneInfo("Asia/Seoul")
    mock_now = datetime(2025, 6, 7, 12, 0, 0, tzinfo=kst).astimezone(timezone.utc)
    
    with patch("backend.services.market_service.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = datetime

        response = await client.get("/api/v1/market/status")
        data = response.json()
        
        assert data["krx"] == "CLOSED"
        assert data["us"] == "CLOSED"
        assert data["crypto"] == "OPEN"
