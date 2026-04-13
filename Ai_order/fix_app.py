import sys

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_head = """import os
import sys
import json
import time
import socket
import random
import uuid
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit
from sqlalchemy import func, desc, text
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()

# 로컬 MQutils 임포트 (가상환경 배포 최적화)
import os
import sys

# 현재 파일이 위치한 디렉토리를 최우선 탐색 경로로 추가
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    # 로컬 폴더(C:\\Users\\USER\\Dev\\왕궁중화요리\\MQutils)에서 임포트 시도
    from MQutils import SolapiMessenger, get_local_ip
except (ImportError, ModuleNotFoundError) as e:
    print(f"[Warning] Local MQutils not found in {BASE_DIR}. Trying fallback. ({str(e)})")
    # Fallback 로직
    from socket import gethostname
    import socket
    get_local_ip = lambda: socket.gethostbyname(gethostname())
    class SolapiMessenger: 
        def __init__(self, *args, **kwargs): pass
        def send_sms(self, *args): print("[Sim] SMS disabled (MQutils missing)")

from models import db, Order, OrderItem, Waiting, Store, User, SystemConfig

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SECRET_KEY'] = 'suragol-secret!'

db_url = os.environ.get('DATABASE_URL', 'sqlite:///suragol.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

"""

# Find the start of the rest of the file.
# The original lines 1-40 contain import and MQutils block.
# My `new_head` replaces lines 1-47 approx.
# Let's find where `app.wsgi_app` or similar starts.
start_idx = -1
for i, line in enumerate(lines):
    if 'app.wsgi_app' in line or 'ProxyFix' in line:
        start_idx = i
        break

if start_idx != -1:
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(new_head)
        f.writelines(lines[start_idx:])
    print("app.py repaired successfully")
else:
    print("Could not find start point in app.py")
