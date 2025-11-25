FROM python:3.11-slim

WORKDIR /app

# 빌드 의존성 설치
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# requirements.txt 위치가 backend 폴더 안이라면 경로 주의
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사 (현재 폴더인 backend 내용을 컨테이너의 /app/backend로 복사)
# 구조상 /app/backend 가 되도록 복사해야 import backend.app... 이 작동함
COPY . /app/backend

# PYTHONPATH 설정
ENV PYTHONPATH=/app

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]