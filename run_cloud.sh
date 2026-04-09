#!/bin/bash

# [포트 설정] Render가 동적으로 할당하는 PORT 환경변수를 사용 (기본값: 10000)
APP_PORT=${PORT:-10000}

echo "🚀 [Step 1/2] SaaS 웹 서버(Port: ${APP_PORT})를 가동합니다..."

# gunicorn으로 실행 - eventlet 워커 1개, 소켓 호환 모드
gunicorn --worker-class eventlet -w 1 --timeout 120 \
         --bind 0.0.0.0:${APP_PORT} \
         app:app 2>&1 | tee server_run.log &

# 서버가 완전히 뜰 때까지 대기 (15초 - DB 초기화 포함)
echo "⏳ 서버 초기화 중... (15초 대기)"
sleep 15

# [Cloudflare Tunnel] 서버와 동일한 포트(APP_PORT)로 연결
echo "🔗 [Step 2/2] 도메인 터널(Cloudflare)을 연결 중입니다..."
if [ -z "$CLOUDFLARE_TUNNEL_TOKEN" ]; then
    echo "⚠️ [Warning] 토큰이 없습니다. 도메인 연결 없이 로컬 접속만 가능합니다."
    wait
else
    cloudflared tunnel --no-autoupdate run --token "$CLOUDFLARE_TUNNEL_TOKEN"
fi
