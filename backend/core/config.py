import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # 1. DB 설정 (기본값은 로컬용이나, Docker 환경변수가 있으면 덮어씌워짐)
    DATABASE_URL: str = "postgresql://devuser:devpass@localhost:5432/dev_db"
    
    # 2. 보안 설정
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ADMIN_EMAIL: str = "admin@stonks.com"
    API_KEY_RATE_LIMIT_PER_MINUTE: int = 120  # 기본 API Key 사용 제한
    
    # 3. 추가된 인프라 설정 (Redis, RabbitMQ)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    
    RABBITMQ_HOST: str = "localhost"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASS: str = "guest"

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