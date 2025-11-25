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
dev-init-db:
	docker-compose -f docker-compose.dev.yml run --rm api python -m backend.create_tables

# 5. 프론트엔드 실행 (별도 터미널 권장)
dev-front:
	cd frontend && npm run dev


# --- 배포 (Deployment Help) ---
# 변경사항을 Github으로 푸시 (배포 트리거)
deploy:
	git add .
	git commit -m "Auto Deploy via Makefile"
	git push origin main