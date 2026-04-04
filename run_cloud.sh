#!/bin/bash

# 1. 8888번 포트로 Flask 서버 실행 (Background)
echo "🚀 [Step 1/2] SaaS 웹 서버를 가동 중입니다..."
python app.py &

# 2. 서버가 뜰 때까지 잠시 대기 (5초)
sleep 5

# 3. Cloudflare Tunnel 가동 (Foreground)
# .env 또는 Render 환경 변수 대시보드에 CLOUDFLARE_TUNNEL_TOKEN이 담겨 있어야 합니다.
echo "🔗 [Step 2/2] 도메인 터널(Cloudflare)을 연결 중입니다..."
if [ -z "$CLOUDFLARE_TUNNEL_TOKEN" ]; then
    echo "⚠️ [Warning] 토큰이 없습니다. 도메인 연결 없이 로컬 접속만 가능합니다."
    # 토큰이 없으면 앱 서버를 포그라운드로 전환하여 유지
    wait
else
    cloudflared tunnel --no-autoupdate run --token "$CLOUDFLARE_TUNNEL_TOKEN"
fi
