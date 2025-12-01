import os
import subprocess
import boto3
import asyncio
from datetime import datetime
from botocore.exceptions import ClientError
from sqlalchemy import text
from backend.core.database import AsyncSessionLocal
from backend.core.config import settings
from backend.core.notify import send_ntfy_notification

async def perform_db_backup():
    """
    PostgreSQL 데이터베이스를 덤프하고 MinIO(S3)에 업로드합니다.
    """
    if not settings.S3_ENDPOINT_URL:
        print("[Backup] S3 configuration missing. Skipping backup.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_stonks_{timestamp}.sql"
    file_path = f"/tmp/{filename}"

    # 1. pg_dump 실행
    # 주의: 암호는 PGPASSWORD 환경변수나 .pgpass 파일로 처리해야 안전함.
    # 여기서는 간단히 PGPASSWORD를 env로 주입하여 실행.
    db_url = settings.DATABASE_URL
    # URL 파싱 (postgresql://user:pass@host:port/db)
    # 실제 운영 환경에서는 파싱 로직을 더 견고하게 짜거나 별도 설정을 써야 함.
    try:
        # DATABASE_URL에서 user, password, host, dbname 추출
        # 예: postgresql://devuser:devpass@postgres:5432/dev_db
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        username = parsed.username
        password = parsed.password
        hostname = parsed.hostname
        port = parsed.port
        dbname = parsed.path[1:]

        env = os.environ.copy()
        env["PGPASSWORD"] = password

        cmd = [
            "pg_dump",
            "-h", hostname,
            "-p", str(port),
            "-U", username,
            "-F", "c", # Custom format (압축됨)
            "-b",      # Blobs 포함
            "-v",      # Verbose
            "-f", file_path,
            dbname
        ]
        
        print(f"[Backup] Starting pg_dump for {dbname}...")
        # subprocess.run은 동기 함수이므로, 메인 루프를 막지 않으려면 executor 등에서 실행해야 하지만,
        # 백업은 드물게 돌므로 일단 간단히 처리. (혹은 run_in_executor 사용)
        process = await asyncio.to_thread(
            subprocess.run, cmd, env=env, capture_output=True, text=True
        )

        if process.returncode != 0:
            raise Exception(f"pg_dump failed: {process.stderr}")
        
        print(f"[Backup] Dump created at {file_path}. Uploading to S3...")

        # 2. S3(MinIO) 업로드
        s3 = boto3.client(
            's3',
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY
        )

        # 버킷 존재 확인 및 생성
        try:
            s3.head_bucket(Bucket=settings.S3_BUCKET_NAME)
        except ClientError:
            s3.create_bucket(Bucket=settings.S3_BUCKET_NAME)
        
        s3.upload_file(file_path, settings.S3_BUCKET_NAME, f"db_backups/{filename}")
        print(f"[Backup] Successfully uploaded to {settings.S3_BUCKET_NAME}/db_backups/{filename}")
        
        # 3. 임시 파일 삭제
        os.remove(file_path)
        
        await send_ntfy_notification(f"✅ DB Backup Successful: {filename}", title="Backup Report")

    except Exception as e:
        error_msg = f"Backup failed: {str(e)}"
        print(f"❌ {error_msg}")
        await send_ntfy_notification(error_msg, title="Backup Failed", priority="high")
        # 임시 파일 정리
        if os.path.exists(file_path):
            os.remove(file_path)

async def cleanup_old_candles():
    """
    오래된 1분봉 데이터(Candle)를 삭제하여 DB 용량을 확보합니다.
    설정된 보존 기간(CANDLE_RETENTION_DAYS) 이전 데이터 삭제.
    """
    days = settings.CANDLE_RETENTION_DAYS
    print(f"[Cleanup] Starting cleanup for candles older than {days} days...")
    
    try:
        async with AsyncSessionLocal() as session:
            # 1분봉만 삭제 대상으로 함 (일봉, 주봉은 보존 가치가 높음)
            query = text(f"""
                DELETE FROM candles 
                WHERE resolution = '1m' 
                AND timestamp < NOW() - INTERVAL '{days} days'
            """)
            result = await session.execute(query)
            await session.commit()
            
            deleted_count = result.rowcount
            print(f"[Cleanup] Deleted {deleted_count} old 1m candles.")
            
            if deleted_count > 0:
                 await send_ntfy_notification(f"🧹 Cleaned up {deleted_count} old candles.", title="Maintenance Report")
            
    except Exception as e:
        print(f"[Cleanup] Failed: {e}")
        await send_ntfy_notification(f"Cleanup failed: {e}", title="Maintenance Error", priority="high")
