import os
import sys

# [강제 경로 보정] 가상환경(venv) 내부 부품을 최우선으로 찾도록 설정
_venv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Lib", "site-packages")
if os.path.exists(_venv_path) and _venv_path not in sys.path:
    sys.path.insert(0, _venv_path)

import subprocess
import time
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

def run_command(cmd):
    pip_path = os.path.join(".venv", "Scripts", "pip.exe")
    site_packages = os.path.join(".venv", "Lib", "site-packages")
    if os.path.exists(pip_path) and "install" in cmd:
        # 가상환경의 site-packages를 명시적으로 타겟으로 지정
        cmd = cmd.replace("pip", f'"{pip_path}"') + f' --target="{site_packages}"'
    return subprocess.run(cmd, shell=True)

def main():
    # 화면 초기화 (윈도우용)
    os.system('cls')
    
    print("\n" + "="*70)
    print(" 🚀 왕궁중화요리 통합 관리 시스템 (도메인 연결 최적화 모드)")
    print("="*70)

    # 1. 필수 부품 점검
    try:
        import requests
        import dotenv
        import flask_apscheduler
        try:
            import psycopg2
        except ImportError:
            import pg8000
    except ImportError as e:
        print(f"\n⚠️ [오류 상세] 다음 부품이 아직 준비되지 않았습니다: {e}")
        print("\n[1/3] 필수 부품(Library)이 부족하여 설치 중입니다 (약 20초 소요)...")
        print(" > 가상환경 시스템 강제 복구를 시도합니다...")
        
        # 1. 엉킨 핵심 패키지들을 가상환경 정중앙에 강제 재설치
        run_command("pip install --upgrade --force-reinstall requests python-dotenv Flask-SocketIO Flask-APScheduler eventlet flask-sqlalchemy")
        
        # 2. 호환성 높은 pg8000 설치
        try:
            print(" > 데이터베이스 엔진(pg8000)을 설치하는 중...")
            run_command("pip install pg8000")
        except: pass
        
        print("\n ✅ 조치가 끝났습니다! 프로그램을 다시 시작해 보세요.")
        input("\n 엔터를 누르면 종료됩니다...")
        return

    # 2. 터널 토큰 입력 (깨끗한 화면에서 수행)
    env_token = os.getenv("CLOUDFLARE_TUNNEL_TOKEN")
    
    if env_token:
        # handle 'cloudflared.exe service install <TOKEN>' safely
        if "service install" in env_token:
            token = env_token.split("service install")[-1].strip().strip('"').strip("'")
        else:
            token = env_token.strip()
        print(f"\n✅ .env 파일에서 토큰을 발견했습니다.")
        print(f" > 토큰: {token[:10]}...{token[-10:]}")
    else:
        print("\n" + "#"*70)
        print(" 💡 [단계 1] Cloudflare Tunnel Token을 입력해 주세요.")
        print(" (Cloudflare 대시보드에서 복사하신 긴 토큰을 여기에 붙여넣으세요)")
        print(" - 토큰 입력 시: https://wang.chicvill.store (고정 주소)")
        print(" - 그냥 엔터(Enter) 시: 임시 보안 주소 생성 (Hands-free 모드)")
        print("#"*70 + "\n")
        
        try:
            raw_input = input(" ▶ 입력 (또는 엔터): ").strip()
            
            # 1. 아무것도 입력 안 한 경우
            if not raw_input:
                token = ""
            # 2. 주소를 잘못 붙여넣은 경우
            elif raw_input.startswith("http"):
                print("\n ⚠️ [주의] 주소가 아니라 '토큰'을 입력해야 합니다.")
                token = ""
            # 3. 'service install <TOKEN>' 형식으로 붙여넣은 경우
            elif "service install" in raw_input:
                token = raw_input.split("service install")[-1].strip().strip('"').strip("'")
            # 4. '--token <TOKEN>' 형식으로 붙여넣은 경우
            elif "--token" in raw_input:
                token = raw_input.split("--token")[-1].strip().split()[0].strip('"').strip("'")
            # 5. 토큰만 바로 붙여넣은 경우
            else:
                token = raw_input.strip('"').strip("'")
        except (EOFError, KeyboardInterrupt):
            print("\n🛑 사용자에 의해 종료되었습니다.")
            return

    # 3. 서버 실행 (터미널에 직접 로그 출력하여 에러 확인)
    print("\n[2/3] 내부 서버를 가동 중입니다 (실시간 에러 확인 모드)...")
    try:
        # 로그 파일 대신 터미널로 직접 출력
        server_proc = subprocess.Popen(
            [sys.executable, "app.py"], 
            text=True
        )
        time.sleep(2) # 서버 가동 확인 대기 시간을 2초로 단축 (이제 즉시 뜹니다)
        print(" > 서버 가동 시도 중...")
    except Exception as e:
        print(f"❌ 서버 가동 실패: {e}")
        return

    # 4. 보안 터널 가동
    print("\n[3/3] 보안 연결을 수립합니다. 잠시만 기다려 주세요...")
    cf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloudflared.exe")
    
    if token:
        print(f"\n✨ 고정 주소로 안전한 통로를 만들고 있습니다...")
        # 토큰 방식은 'tunnel run'이 가장 확실합니다.
        cmd = [cf_path, "tunnel", "run", "--token", token, "--protocol", "http2"]
    else:
        print(f"\n✨ 임시 보안 주소를 생성합니다. (Handshake 중...)")
        # 토큰 없을 땐 'tunnel --url' 보다 '--url'만 쓰는 게 더 잘 될 때가 있습니다.
        cmd = [cf_path, "tunnel", "--url", "http://127.0.0.1:10000", "--protocol", "http2"]

    print(f"\n[실행 명령어]: {' '.join(cmd)}")
    print("-" * 70)

    try:
        # 터널 실행 (무한 반복으로 재시작 지원)
        while True:
            try:
                subprocess.run(cmd)
                print("\n⚠️ 보안 터널(Cloudflare)이 예상치 못하게 종료되었습니다.")
                print(" > 5초 후 자동으로 다시 연결을 시도합니다...")
                time.sleep(5)
            except KeyboardInterrupt:
                raise
    except KeyboardInterrupt:
        print("\n\n🛑 보안 연결을 종료합니다.")
    finally:
        server_proc.terminate()
        print("✅ 모든 시스템이 안전하게 종료되었습니다.")

if __name__ == "__main__":
    main()
