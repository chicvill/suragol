import subprocess
import sys
import os
import time
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

def run_command(cmd):
    pip_path = os.path.join(".venv", "Scripts", "pip")
    if os.path.exists(pip_path):
        cmd = cmd.replace("pip", pip_path)
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
    except ImportError:
        print("\n[1/3] 필수 부품이 부족하여 설치 중입니다 (약 10초 소요)...")
        run_command("pip install requests python-dotenv")
        print(" > 설치 완료! 프로그램을 다시 시작해 주세요.")
        input("\n 엔터를 누르면 종료됩니다...")
        return

    # 2. 터널 토큰 입력 (깨끗한 화면에서 수행)
    env_token = os.getenv("CLOUDFLARE_TUNNEL_TOKEN")
    
    if env_token:
        print(f"\n✅ .env 파일에서 토큰을 발견했습니다.")
        print(f" > 토큰: {env_token[:10]}...{env_token[-10:]}")
        token = env_token
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

    # 3. 서버 실행 (로그를 파일로 분리하여 화면을 깨끗하게 유지)
    print("\n[2/3] 내부 서버를 가동 중입니다...")
    import subprocess
    log_file = open("server.log", "w", encoding='utf-8')
    server_proc = subprocess.Popen(
        [sys.executable, "app.py"], 
        stdout=log_file, 
        stderr=log_file,
        text=True
    )
    time.sleep(3)
    print(" > 서버 가동 완료 (로그는 server.log에서 확인 가능)")

    # 4. 보안 터널 가동
    print("\n[3/3] 보안 연결을 수립합니다. 잠시만 기다려 주세요...")
    cf_path = r"C:\Users\USER\Dev\YTDownloader_v2\cloudflared.exe"
    
    if token:
        print(f"\n✨ 고정 주소로 안전한 통로를 만들고 있습니다...")
        # 토큰 방식은 'tunnel run'이 가장 확실합니다.
        cmd = [cf_path, "tunnel", "run", "--token", token]
    else:
        print(f"\n✨ 임시 보안 주소를 생성합니다. (Handshake 중...)")
        # 토큰 없을 땐 'tunnel --url' 보다 '--url'만 쓰는 게 더 잘 될 때가 있습니다.
        cmd = [cf_path, "tunnel", "--url", "http://127.0.0.1:8888"]

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
        log_file.close()
        print("✅ 모든 시스템이 안전하게 종료되었습니다.")

if __name__ == "__main__":
    main()
