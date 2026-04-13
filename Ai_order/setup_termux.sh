#!/bin/bash
echo "================================================="
echo " 🍜 왕궁중화요리 Termux 자동 설치 스크립트"
echo "================================================="

# 1. 저장소 권한 요청 (최초 1회)
termux-setup-storage
sleep 2

# 2. 다운로드 폴더에서 홈 디렉토리로 이동
echo "[1/4] Download 폴더에서 파일을 가져옵니다..."
# 기존 폴더가 있으면 안전하게 백업
if [ -d ~/왕궁중화요리 ]; then
    mv ~/왕궁중화요리 ~/왕궁중화요리_backup_$(date +%s)
fi
cp -rf ~/storage/downloads/왕궁중화요리 ~/왕궁중화요리
cd ~/왕궁중화요리

# 3. 스마트폰(Termux)용 파이썬 환경 설정
echo "[2/4] 파이썬 및 필수 패키지를 설치합니다..."
pkg update -y
pkg install python -y
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. 실행 스크립트 실행 권한 부여
echo "[3/4] 실행 권한을 부여합니다..."
chmod +x run_termux.sh

echo "================================================="
echo " 🎉 설치가 완료되었습니다!"
echo ""
echo " 이제 아래 명령어를 입력하여 서버와 터널을 동시에 켜세요:"
echo " 👉 cd ~/왕궁중화요리 && ./run_termux.sh"
echo "================================================="
