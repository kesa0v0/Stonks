# 1. Build Stage
FROM node:18-alpine AS builder
WORKDIR /app
# 패키지 정보만 먼저 복사 (캐싱 활용)
COPY package.json package-lock.json ./
RUN npm install
# 소스 복사 및 빌드
COPY . .
RUN npm run build

# 2. Run Stage (Nginx)
FROM nginx:alpine
# 빌드된 결과물(dist 또는 build 폴더)을 Nginx가 서빙할 폴더로 복사
# (Vite를 쓰면 보통 dist, CRA는 build 폴더입니다. 확인 필요!)
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx 설정 파일 복사 (SPA 라우팅 지원)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]