@echo off
:: UTF-8 인코딩 설정 (한글 깨짐 방지)
chcp 65001 >nul
setlocal

echo ==========================================
echo   왕궁중화요리 - Docker 실행 환경 검사
echo ==========================================
echo.

:: Docker 명령어 존재 여부 확인
where docker >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Docker가 설치되어 있지 않거나 PATH에 항목이 없습니다.
    echo Docker Desktop을 먼저 설치해 주세요. (https://www.docker.com/products/docker-desktop)
    echo.
    pause
    exit /b
)

echo [1/3] Docker 엔진 상태 확인 중...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [오류] Docker 엔진이 실행 중이지 않습니다!
    echo.
    echo 다음 사항을 확인해 주세요:
    echo 1. Docker Desktop 앱을 실행해 주세요.
    echo 2. 하단 트레이의 Docker 아이콘이 'Docker is running' 상태인지 확인해 주세요.
    echo.
    pause
    exit /b
)

echo [2/3] Docker 이미지 빌드 중... (잠시만 기다려 주세요)
docker build -t wang-gung-app .

echo [3/3] 컨테이너 실행 중 (포트: 8888)...
echo.
echo 브라우저에서 http://localhost:8888 으로 접속하세요.
echo.
docker run -p 8888:8888 --name wang-gung-container --rm wang-gung-app

pause
