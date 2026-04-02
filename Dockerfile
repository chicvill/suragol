# Render 및 클라우드 배포용 Dockerfile
FROM python:3.10-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 의존성 설치 (psycopg2 빌드 등에 필요할 수 있음)
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# 요구사항 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스 복사
COPY . .

# Render는 기본 환경변수로 PORT를 할당합니다.
EXPOSE $PORT

# Eventlet 기반 Gunicorn 실행 (SocketIO 완벽 호환)
CMD gunicorn -k eventlet -w 1 -b 0.0.0.0:$PORT app:app
