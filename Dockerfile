# 1단계: Cloudflare 공식 이미지에서 실행 파일 복사
FROM cloudflare/cloudflared:latest as cloudflared_source

# 2단계: 실제 운영용 Python 이미지
FROM python:3.11-slim
COPY --from=cloudflared_source /usr/local/bin/cloudflared /usr/local/bin/cloudflared

# 3. 환경 설정
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# [수정] Render가 동적으로 포트를 10000번으로 지정하므로 기본값 맞춤
ENV PORT 10000

WORKDIR /app

# 4. 앱 종속성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 소스 복사 및 시작 스크립트 권한 부여
COPY . .
RUN chmod +x run_cloud.sh

# 6. 포트 오픈 (Render 기본 포트 10000)
EXPOSE 10000

# 7. 서버와 터널을 동시에 실행하는 쉘 스크립트 호출
CMD ["./run_cloud.sh"]
