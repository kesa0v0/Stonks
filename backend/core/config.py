import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DEBUG : bool = True
    ENVIRONMENT: str = "development"  # production, staging, development
    RATE_LIMIT_ENABLED: bool = False

    # 1. DB 설정 (Docker 기본값: 서비스명 사용, 환경변수로 덮어쓰기 가능)
    # 로컬 호스트에서 직접 실행할 경우 .env 또는 환경변수로 localhost로 변경하세요.
    DATABASE_URL: str = "postgresql://devuser:devpass@postgres:5432/dev_db"
    
    # 2. 보안 설정
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ADMIN_EMAIL: str = "admin@stonks.com"
    ADMIN_PASSWORD: str = "admin"
    API_KEY_RATE_LIMIT_PER_MINUTE: int = 120  # 기본 API Key 사용 제한
    
    # 3. 추가된 인프라 설정 (Redis, RabbitMQ)
    # Docker 네트워크 기본값 (로컬 실행 시 .env로 덮어쓰기)
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    
    RABBITMQ_HOST: str = "rabbitmq"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASS: str = "guest"

    # 4. Discord 설정
    DISCORD_CLIENT_ID: str = ""
    DISCORD_CLIENT_SECRET: str = ""
    DISCORD_REDIRECT_URI: str = "http://localhost:5173/auth/discord/callback"
    DISCORD_GUILD_ID: str = ""  # If set, only allow members of this Guild ID
    # Bot/알림용 (옵션)
    DISCORD_BOT_TOKEN: str = ""
    DISCORD_ALERTS_WEBHOOK_URL: str = ""      # 일반 알림 채널(청산/고래/리포트)
    DISCORD_HUMAN_WEBHOOK_URL: str = ""       # Human ETF 전용 채널(IPO/배당/구제금융)
    # 알림 임계치/스케줄
    WHALE_ALERT_THRESHOLD_KRW: int = 10_000_000
    DAILY_REPORT_CRON_KST: str = "0 0 * * *"   # 매일 00:00 KST

    # 5. Observability
    NTFY_URL: str = "https://ntfy.sh"
    NTFY_TOPIC: str = "stonks_dev_errors"
    NTFY_ENABLED: bool = True

    # 6. Backup & Storage (MinIO/S3)
    S3_ENDPOINT_URL: str = "http://minio:9000" # Docker 내부 통신용
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "stonks-backups"
    BACKUP_RETENTION_DAYS: int = 30 # 로컬/S3 백업 파일 보관 기간
    CANDLE_RETENTION_DAYS: int = 90 # DB 내 1분봉 보관 기간

    # 7. CORS 허용 오리진 (배포시 환경변수로 덮어쓰기)
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174"
    ]

    DEBUG: bool = True

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

    model_config = SettingsConfigDict(
        # Pydantic은 운영체제 환경변수(Docker가 넣어준 값)를 1순위로 읽고,
        # 없으면 아래 파일(.env)을 찾습니다.
        # Docker Compose에서 env_file을 지정했으므로 이 설정은 '로컬 실행용' 보험입니다.
        env_file = ".env",
        # .env 파일에 정의되지 않은 추가 변수가 있어도 에러 내지 않음
        extra = "ignore" 
    )

settings = Settings()