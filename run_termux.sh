#!/bin/bash
echo "================================================="
echo " 🚀 왕궁중화요리 스마트폰/Pad 동시 서버 구동"
echo "================================================="

cd ~/왕궁중화요리
source venv/bin/activate

# 1. 터널 토큰 읽어오기 (.env 파일에서)
if [ ! -f .env ]; then
    echo "⚠️ .env 파일이 없습니다! 토큰을 설정해 주세요."
    exit 1
fi

TOKEN=$(grep CLOUDFLARE_TUNNEL_TOKEN .env | cut -d '=' -f2 | tr -d '\r')

if [ -z "$TOKEN" ]; then
    echo "⚠️ .env 파일에 터널 접속 토큰이 비어 있습니다."
    exit 1
fi

# 2. 파이썬 서버 백그라운드 구동 (포트 8888)
echo "[1/2] 파이썬 서버(app.py)를 백그라운드로 켭니다..."
python app.py > server_termux.log 2>&1 &
SERVER_PID=$!
sleep 2

# 파이썬 서버가 잘 커졌는지 확인
if ps -p $SERVER_PID > /dev/null
then
   echo " > 서버가 포트 8888번에서 성공적으로 열렸습니다!"
else
   echo "⚠️ 파이썬 서버가 켜지다 꺼졌습니다. 코드 에러를 확인하세요."
   exit 1
fi

# 3. 브라우저/터미널 종료 후에도 안전하게 서버를 내리기 위한 트랩 설정
cleanup() {
    echo ""
    echo "🛑 모든 시스템을 종료합니다..."
    kill $SERVER_PID
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 4. Cloudflare 멀티 터널 구동 (백그라운드 터널과 충돌 없이 스마트폰 통신망 개방)
echo ""
echo "[2/2] 보안 터널(Cloudflare)을 수립합니다. (스마트폰용)..."
echo " > 토큰 : ${TOKEN:0:15}..."
echo " > 지금부터 wang.chicvill.store 로 접속하시면 이 Pad로 연결됩니다!"
echo "-------------------------------------------------"

# 터널 무한 재시작 로직 (네트워크 끊김 대비)
while true; do
    cloudflared tunnel run --token "$TOKEN"
    echo ""
    echo "⚠️ 보안 연결이 일시적으로 끊어졌습니다. 5초 뒤 복구합니다..."
    sleep 5
done
