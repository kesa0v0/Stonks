# Makefile

# --- 개발 환경 (Local Development) ---

# 1. 인프라 & 백엔드 실행 (백그라운드)
dev-up:
	docker-compose -f docker-compose.dev.yml up -d

# 2. 로그 보기 (실시간)
dev-logs:
	docker-compose -f docker-compose.dev.yml logs -f api

# 3. 개발 환경 종료
dev-down:
	docker-compose -f docker-compose.dev.yml down

# 4. DB 테이블 초기화 (최초 실행 시 1회 필수)
dev-init-db: db-upgrade
	docker-compose -f docker-compose.dev.yml run --rm api python -m backend.create_test_user
	docker-compose -f docker-compose.dev.yml run --rm api python -m backend.create_tickers

# 5. DB 마이그레이션 실행
db-upgrade:
	# backend/alembic.ini를 명시적으로 사용해 localhost 하드코딩을 피합니다.
	docker-compose -f docker-compose.dev.yml run --rm api alembic -c backend/alembic.ini upgrade head

# 5. 프론트엔드 실행 (별도 터미널 권장)
dev-front:
	cd frontend && npm run dev


# --- 배포 (Deployment Help) ---
# 변경사항을 Github으로 푸시 (배포 트리거)
deploy:
	git add .
	git commit -m "Auto Deploy via Makefile"
	git push origin main


# --- Tests ---
.PHONY: test-sqlite test-pg test-pg-docker

# 로컬 Python 환경(가상환경 활성화 전제)에서 SQLite(in-memory)로 빠르게 테스트
test-sqlite:
	@echo "[tests] Running with SQLite (in-memory)"
	TEST_DB=sqlite pytest -q backend

# 로컬 Python 환경에서 Docker dev Postgres에 붙어 테스트 (필요시 컨테이너 기동)
test-pg:
	@echo "[tests] Ensuring dev postgres is up..."
	docker-compose -f docker-compose.dev.yml up -d postgres
	@echo "[tests] Running against Docker Postgres"
	TEST_DB=pg pytest -q backend

# 컨테이너(api) 안에서 테스트 실행 (로컬 파이썬/venv 불필요)
test-pg-docker:
	@echo "[tests] Running inside api container against dev Postgres"
	docker-compose -f docker-compose.dev.yml run --rm -e TEST_DB=pg api pytest -q backend