import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend.worker.maintenance import perform_db_backup, cleanup_old_candles
from backend.core.config import settings

@pytest.mark.asyncio
async def test_perform_db_backup_success():
    """
    백업 프로세스가 정상적으로 pg_dump를 호출하고 S3에 업로드하는지 테스트
    """
    # 1. 설정 Mocking
    with patch.object(settings, 'S3_ENDPOINT_URL', 'http://mock-s3'), \
         patch.object(settings, 'S3_BUCKET_NAME', 'test-bucket'), \
         patch.object(settings, 'DATABASE_URL', 'postgresql://u:p@h:5432/db'):
        
        # 2. subprocess.run (pg_dump) Mocking
        # returncode=0 (성공)
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stderr = ""
        
        # 3. boto3 client Mocking
        mock_s3 = MagicMock()
        
        # 4. asyncio.to_thread Mocking (subprocess 실행 부분)
        with patch('asyncio.to_thread', return_value=mock_process) as mock_run, \
             patch('boto3.client', return_value=mock_s3) as mock_boto, \
             patch('os.remove') as mock_remove, \
             patch('backend.worker.maintenance.send_ntfy_notification', new_callable=AsyncMock) as mock_notify:
            
            await perform_db_backup()
            
            # 검증: pg_dump 실행 확인
            mock_run.assert_called_once()
            args, _ = mock_run.call_args
            cmd = args[1] # args[0] is subprocess.run func
            assert cmd[0] == "pg_dump"
            assert "db" in cmd # dbname check
            
            # 검증: S3 업로드 확인
            mock_s3.upload_file.assert_called_once()
            # bucket name check
            assert mock_s3.upload_file.call_args[0][1] == 'test-bucket'
            
            # 검증: 성공 알림 전송
            mock_notify.assert_called()
            assert "Successful" in mock_notify.call_args[0][0]

@pytest.mark.asyncio
async def test_perform_db_backup_skip_if_no_s3():
    """
    S3 설정이 없으면 백업을 스킵하는지 테스트
    """
    with patch.object(settings, 'S3_ENDPOINT_URL', None):
        with patch('asyncio.to_thread') as mock_run:
            await perform_db_backup()
            mock_run.assert_not_called()

@pytest.mark.asyncio
async def test_perform_db_backup_failure():
    """
    pg_dump 실패 시 에러 알림을 보내는지 테스트
    """
    with patch.object(settings, 'S3_ENDPOINT_URL', 'http://mock-s3'):
        # 실패 시뮬레이션 (returncode != 0)
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stderr = "pg_dump error"
        
        with patch('asyncio.to_thread', return_value=mock_process), \
             patch('backend.worker.maintenance.send_ntfy_notification', new_callable=AsyncMock) as mock_notify:
            
            await perform_db_backup()
            
            # 에러 알림 전송 확인
            mock_notify.assert_called()
            assert "failed" in mock_notify.call_args[0][0]

@pytest.mark.asyncio
async def test_cleanup_old_candles():
    """
    오래된 캔들 삭제 쿼리가 실행되는지 테스트
    """
    # DB 세션 및 execute 결과 Mocking
    mock_result = MagicMock()
    mock_result.rowcount = 100
    
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    
    # async context manager (__aenter__) 처리
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    
    with patch('backend.worker.maintenance.AsyncSessionLocal', mock_session_factory), \
         patch('backend.worker.maintenance.send_ntfy_notification', new_callable=AsyncMock) as mock_notify:
        
        await cleanup_old_candles()
        
        # 쿼리 실행 확인
        mock_session.execute.assert_called_once()
        # DELETE 문 포함 여부 확인
        executed_query = str(mock_session.execute.call_args[0][0])
        assert "DELETE FROM candles" in executed_query
        
        # 알림 전송 확인 (삭제된 건수가 있으므로)
        mock_notify.assert_called()
        assert "Cleaned up 100" in mock_notify.call_args[0][0]
