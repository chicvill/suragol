import os
import shutil
import re

# 1. 대상 폴더 설정
source_dir = os.path.dirname(os.path.abspath(__file__))
target_dir = os.path.abspath(os.path.join(source_dir, '..', 'FreeOrder'))

print(f"🚀 프로젝트 마이그레이션을 시작합니다.")
print(f"👉 원본: {source_dir}")
print(f"👉 대상: {target_dir}")

# 2. 파일 복사 (가상환경 및 불필요한 파일 제외)
if not os.path.exists(target_dir):
    os.makedirs(target_dir)

def ignore_patterns(path, names):
    return set(['.venv', 'venv', '__pycache__', 'instance', 'wang_gung.db', 'server.log', '.git', 'screenshot'])

try:
    shutil.copytree(source_dir, target_dir, ignore=ignore_patterns, dirs_exist_ok=True)
    print("✅ 파일 복사 완료")
except Exception as e:
    print(f"❌ 파일 복사 실패: {e}")
    exit(1)

# 3. app.py 수정 (Supabase PostgreSQL 지원 추가 및 ProxyFix 강화)
app_py_path = os.path.join(target_dir, 'app.py')
with open(app_py_path, 'r', encoding='utf-8') as f:
    app_data = f.read()

# DB 연결 문자열 수정
db_uri_pattern = r"app\.config\['SQLALCHEMY_DATABASE_URI'\]\s*=\s*'sqlite:///wang_gung\.db'"
db_uri_replacement = """# Supabase PostgreSQL 및 기본 SQLite 지원
db_url = os.environ.get('DATABASE_URL', 'sqlite:///wang_gung.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url"""

if "DATABASE_URL" not in app_data:
    app_data = re.sub(db_uri_pattern, db_uri_replacement, app_data)

# 포트 자동 할당 (Render는 PORT 환경변수 제공하므로 0.0.0.0 사용)
port_pattern = r"port\s*=\s*8888"
port_replacement = "port = int(os.environ.get('PORT', 8888))"
if "os.environ.get('PORT'" not in app_data:
    app_data = re.sub(port_pattern, port_replacement, app_data)

with open(app_py_path, 'w', encoding='utf-8') as f:
    f.write(app_data)
print("✅ app.py 클라우드/데이터베이스 설정 패치 완료")

# 4. requirements.txt 업데이트 (PostgreSQL 드라이버 및 Gunicorn 추가)
req_path = os.path.join(target_dir, 'requirements.txt')
reqs = []
if os.path.exists(req_path):
    with open(req_path, 'r', encoding='utf-8') as f:
        reqs = f.read().splitlines()

new_reqs = ['psycopg2-binary==2.9.9', 'gunicorn==21.2.0', 'eventlet==0.33.3']
added = False
for nr in new_reqs:
    if not any(nr.split('==')[0] in r for r in reqs):
        reqs.append(nr)
        added = True

if added:
    with open(req_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(reqs) + "\n")
    print("✅ requirements.txt (psycopg2, gunicorn, eventlet) 추가 완료")

# 5. Dockerfile 생성 (Render 디플로이용 최적화)
dockerfile_path = os.path.join(target_dir, 'Dockerfile')
dockerfile_content = """# Render 및 클라우드 배포용 Dockerfile
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
"""
with open(dockerfile_path, 'w', encoding='utf-8') as f:
    f.write(dockerfile_content)
print("✅ Dockerfile 생성 완료")

# 6. render.yaml (Render BlueprintsIaC 용 설정 파일)
render_yaml_path = os.path.join(target_dir, 'render.yaml')
render_yaml_content = """services:
  - type: web
    name: free-order
    env: docker
    plan: free # Render 무료 요금제 사용 시
    branch: main
    envVars:
      - key: DATABASE_URL
        sync: false # Supabase에서 발급받은 URI를 Render 대시보드에 직접 입력하세요
"""
with open(render_yaml_path, 'w', encoding='utf-8') as f:
    f.write(render_yaml_content)
print("✅ Render 배포 설정 파일(render.yaml) 생성 완료")

print("\\n🎉 완벽하게 이식 준비가 끝났습니다!")
print("다음 단계를 진행해 주세요:")
print("1. 상단 메뉴 File > Open Folder 를 클릭하여 'FreeOrder' 폴더를 열어주세요.")
print("2. (선택) Supabase에 가입하고 프로젝트를 만들어 Database URL을 획득합니다.")
print("3. 프로젝트를 GitHub에 업로드하고 Render.com 에서 New Web Service를 눌러 연결하면 됩니다.")
