import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.core.notify import send_ntfy_notification
from backend.core.config import settings
from backend.services.order_service import ORDER_COUNTER
from backend.core.enums import OrderSide, OrderType

client = TestClient(app)

@pytest.mark.asyncio
async def test_ntfy_notification_enabled():
    """
    ntfy 설정이 켜져 있을 때 httpx.post가 올바르게 호출되는지 테스트
    """
    # 설정 강제 적용 (Mocking settings)
    with patch.object(settings, 'NTFY_ENABLED', True), \
         patch.object(settings, 'NTFY_URL', 'https://ntfy.sh'), \
         patch.object(settings, 'NTFY_TOPIC', 'test_topic'):
        
        with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            await send_ntfy_notification(
                message="Test Alert",
                title="Test Title",
                priority="high"
            )
            
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            
            assert args[0] == "https://ntfy.sh/test_topic"
            assert kwargs['headers']['Title'] == "Test Title"
            assert kwargs['headers']['Priority'] == "high"
            assert kwargs['data'] == b"Test Alert"

@pytest.mark.asyncio
async def test_ntfy_notification_disabled():
    """
    ntfy 설정이 꺼져 있을 때 호출되지 않는지 테스트
    """
    with patch.object(settings, 'NTFY_ENABLED', False):
        with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            await send_ntfy_notification("Should not send")
            mock_post.assert_not_called()

def test_prometheus_metrics_endpoint():
    """
    /metrics 엔드포인트가 200 OK를 반환하고, 
    커스텀 메트릭(stonks_orders_created_total)이 포함되어 있는지 테스트
    """
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    
    # 기본적인 Python 메트릭 존재 여부 확인
    assert "python_info" in response.text
    
    # 커스텀 메트릭 정의 존재 여부 확인
    assert "stonks_orders_created_total" in response.text

def test_order_counter_increment():
    """
    주문 카운터가 증가하면 /metrics 출력에도 반영되는지 테스트
    """
    # 1. 초기 값 확인 (없을 수도 있음)
    response_before = client.get("/metrics")
    
    # 2. 카운터 강제 증가 (실제 주문 로직 대신 카운터 객체 직접 조작)
    ORDER_COUNTER.labels(side=OrderSide.BUY.value, type=OrderType.LIMIT.value).inc()
    
    # 3. 증가 후 값 확인
    response_after = client.get("/metrics")
    assert response_after.status_code == 200
    
    # "stonks_orders_created_total{side="BUY",type="LIMIT"} 1.0" 형태의 문자열을 찾음
    expected_part = f'stonks_orders_created_total{{side="{OrderSide.BUY.value}",type="{OrderType.LIMIT.value}"}}'
    assert expected_part in response_after.text
