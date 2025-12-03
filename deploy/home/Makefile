# Makefile for Deployment (Production)
# Usage: 
#   make up           (Defaults to home environment)
#   make ENV=oci up   (Targeting OCI environment)

COMPOSE_FILE = docker-compose.yml

.PHONY: up down logs init-db create-admin pull shell

# 1. 최신 이미지 가져오기
pull:
	docker compose -f $(COMPOSE_FILE) pull

# 2. 서비스 실행
up:
	docker compose -f $(COMPOSE_FILE) up -d

# 3. 서비스 종료
down:
	docker compose -f $(COMPOSE_FILE) down

# 4. 로그 확인 (API)
logs:
	docker compose -f $(COMPOSE_FILE) logs -f api

# 5. DB 마이그레이션 (테이블 생성/업데이트)
init-db:
	docker compose -f $(COMPOSE_FILE) run --rm api alembic upgrade head

# 6. 관리자 계정 생성 (backend/create_admin.py 실행)
create-admin:
	docker compose -f $(COMPOSE_FILE) run --rm api python -m backend.create_admin

# 7. 컨테이너 쉘 접속 (디버깅용)
shell:
	docker compose -f $(COMPOSE_FILE) exec api /bin/bash
