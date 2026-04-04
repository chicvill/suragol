# 1. Base Image
FROM python:3.11-slim

# 2. 필수 패키지 및 Cloudflare Tunnel 클라이언트 직접 설치 (안정적인 방식)
RUN apt-get update && apt-get install -y wget curl && \
    curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && \
    dpkg -i cloudflared.deb && \
    rm cloudflared.deb && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 3. 환경 설정
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PORT 8888

WORKDIR /app

# 4. 앱 종속성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 소스 복사 및 시작 스크립트 권한 부여
COPY . .
RUN chmod +x run_cloud.sh

# 6. SaaS 통합 포트 오픈
EXPOSE 8888

# 7. 서버와 터널을 동시에 실행하는 쉘 스크립트 호출
CMD ["./run_cloud.sh"]
