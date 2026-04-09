import os
import sys

# [강제 경로 보정] 로컬(Windows) 환경에서 .venv 내부 부품을 찾도록 설정 (클라우드 환경 배포 시 무시됨)
if sys.platform == 'win32':
    _venv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Lib", "site-packages")
    if os.path.exists(_venv_path) and _venv_path not in sys.path:
        sys.path.insert(0, _venv_path)

import json
import time
import socket
import random
import uuid
import csv
import io
import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------
# 외부 유틸리티 모듈 임포트
# ---------------------------------------------------------
from MQutils.ai_engine import get_ai_recommended_menu, get_ai_operation_insight

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, desc, text, or_
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from dotenv import load_dotenv
from flask_apscheduler import APScheduler
import threading

# 환경변수 로드
load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------
# Flask 앱 및 스케줄러 초기화
# ---------------------------------------------------------
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.jinja_env.add_extension('jinja2.ext.do')  # {% do %} 태그 활성화
scheduler = APScheduler()
scheduler.init_app(app) # 스케줄러와 앱 연결
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1) # HTTPS 프록시 헤더 처리
app.config['SECRET_KEY'] = 'suragol-secret-key-2026'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=3) # 3분 후 자동 로그아웃
app.url_map.strict_slashes = False # URL 끝 슬래시(/) 유무에 상관없이 접속 허용
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'images')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# [DB 설정] 환경변수에 DATABASE_URL이 있으면 우선 사용 (Supabase 등), 없으면 로컬 SQLite 사용
db_url = os.environ.get('DATABASE_URL')

# ---------------------------------------------------------
# DB 연결 설정 및 패치
# ---------------------------------------------------------
if db_url:
    # [호스트 보정] 프로젝트별 고유 호스트명 사용 권장
    # (wdikgmyhuxhhyeljnyqa.supabase.co 형태로 자동 전환 시도 가능하나 일단 전달받은 URL 유지)
    
    if "postgresql://" in db_url or "postgres://" in db_url:
        try:
            # 1순위: psycopg2 시도 (Render/Linux 환경 권장)
            import psycopg2
            print("🐘 [DB 엔진] psycopg2를 사용합니다.")
        except ImportError:
            # 2순위: pg8000 전환 (psycopg2 없는 환경용)
            if "postgresql+pg8000://" not in db_url:
                db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)
                db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
            print("🐘 [DB 엔진] pg8000으로 대체 실행합니다.")

    # 연결 문자열 로깅 (보안 마스킹)
    try:
        from sqlalchemy.engine.url import make_url
        url_obj = make_url(db_url)
        safe_url = f"{url_obj.drivername}://{url_obj.username}:****@{url_obj.host}:{url_obj.port}/{url_obj.database}"
        print(f"🔗 [DB 접속 시도] {safe_url}")
    except Exception:
        print("🔗 [DB 접속 시도] URL 형식을 확인 중입니다...")

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

from models import db, Order, OrderItem, Waiting, Store, User, SystemConfig, TaxInvoice, ServiceRequest, Customer, PointTransaction, Attendance

# SQLALchemy 인스턴스 초기화 (모델의 db 사용)
db.init_app(app)

# [진짜 최종 마이그레이션] PostgreSQL 호환성 및 부족한 컬럼 자동 생성
with app.app_context():
    # 로컬에서 Supabase 접속 시 락(Lock) 충돌 방지를 위해 마이그레이션 건너뛰기 옵션 추가
    if os.environ.get('LOCAL_SKIP_MIGRATION') == 'true':
        print("⏭️ [DB] 마이그레이션을 건너뛰고 바로 연결합니다. (로컬 모드)")
    else:
        print("🔍 [DB 점검] 테이블 및 컬럼 상태를 확인합니다...")
        try:
            db.create_all()
            
            # [컬럼 보강] 반복 로직 통합 처리
            tables_cols = {
                "users": [
                    ("is_approved", "BOOLEAN DEFAULT FALSE"),
                    ("agreed_at", "TIMESTAMP WITH TIME ZONE"),
                    ("full_name", "VARCHAR(100)"),
                    ("phone", "VARCHAR(50)"),
                    ("hourly_rate", "INTEGER DEFAULT 10000"),
                    ("position", "VARCHAR(50)"),
                    ("work_schedule", "JSON"),
                    ("contract_start", "DATE"),
                    ("contract_end", "DATE")
                ],
                "stores": [
                    ("monthly_fee", "INTEGER DEFAULT 50000"),
                    ("attendance_pin", "VARCHAR(255) DEFAULT '0000'"),
                    ("recommended_by", "INTEGER"),
                    ("is_public", "BOOLEAN DEFAULT FALSE"),
                    ("signature_owner", "TEXT"),
                    ("signature_partner", "TEXT"),
                    ("theme_color", "VARCHAR(20) DEFAULT '#3b82f6'"),
                    ("contact_phone", "VARCHAR(50)"),
                    ("point_ratio", "FLOAT DEFAULT 0.0"),
                    ("waiting_sms_no", "VARCHAR(50)"),
                    ("business_type", "VARCHAR(50)"),
                    ("business_item", "VARCHAR(100)"),
                    ("business_email", "VARCHAR(100)"),
                    ("stats_reset_at", "TIMESTAMP WITH TIME ZONE"),
                    ("timezone", "VARCHAR(50) DEFAULT 'Asia/Seoul'")
                ]
            }
            
            for table, cols in tables_cols.items():
                for col, dtype in cols:
                    try:
                        db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}"))
                        db.session.commit()
                    except Exception:
                        db.session.rollback()

            # PIN 자리수 확장 (중요)
            try:
                db.session.execute(text("ALTER TABLE stores ALTER COLUMN attendance_pin TYPE VARCHAR(255)"))
                db.session.commit()
            except Exception:
                db.session.rollback()

            print("🚀 [완료] 데이터베이스 구조 동기화 완료.")
        except Exception as e:
            print(f"❌ [에러] 초기화 중 문제 발생: {e}")


# --- 라우트 및 소켓 초기 설정 ---
from extensions import socketio
socketio.init_app(app)

from sockets import register_socketio_events
register_socketio_events(socketio)

from routes.attendance import attendance_bp
app.register_blueprint(attendance_bp)

from routes.auth import init_auth_routes
init_auth_routes(app)

from routes.admin import init_admin_routes
init_admin_routes(app)

from routes.store import init_store_routes
init_store_routes(app)

from MQutils import (
    login_required, admin_required, staff_required, manager_required, owner_only_required,
    store_access_required, send_waiting_sms, check_nearby_waiting,
    format_phone, calculate_commission, get_staff_performance, send_daily_backup
)

@app.context_processor
def inject_globals():
    return {'timedelta': timedelta, 'now': datetime.now()}

app.jinja_env.filters['format_phone'] = format_phone

# MQnet Central Index
@app.route('/')
def index():
    user_id = session.get('user_id')
    if not user_id:
        return render_template('index.html', logged_in=False)
    
    user = db.session.get(User, user_id)
    if not user:
        session.clear()
        return redirect(url_for('login'))
        
    role = user.role
    store_id = user.store_id
    if role == 'owner' and not store_id:
        managed_store = Store.query.filter_by(recommended_by=user.id).first()
        if managed_store:
            store_id = managed_store.id
            user.store_id = store_id
            db.session.commit()
            session['store_id'] = store_id
            
    store = db.session.get(Store, store_id) if store_id else None
    stores = []
    if role == 'admin':
        stores = Store.query.all()
    elif role == 'staff':
        try:
            stores = Store.query.filter(or_(Store.recommended_by == user_id, Store.is_public == True)).all()
        except:
            stores = Store.query.filter_by(recommended_by=user_id).all()
        
    users_pending = User.query.filter_by(is_approved=False).all()
    return render_template('index.html', logged_in=True, user=user, role=role, store=store, stores=stores, users_pending=users_pending)



@app.errorhandler(403)
def forbidden(e):
    return render_template('access_denied.html'), 403

# ---------------------------------------------------------
# [Keep-Alive] Render 슬립 방지 핑 (10분마다 자기 자신에게 요청)
# ---------------------------------------------------------
def keep_alive_ping():
    """Render 무료 플랜 서버가 잠들지 않도록 주기적으로 자기 자신에게 핑을 보냅니다."""
    import urllib.request
    render_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not render_url:
        return  # 로컬 또는 Render가 아닌 환경에서는 동작하지 않음
    try:
        ping_url = f"{render_url.rstrip('/')}/ping"
        req = urllib.request.urlopen(ping_url, timeout=10)
        print(f"✅ [Keep-Alive] 핑 성공 → {ping_url} (HTTP {req.status})")
    except Exception as e:
        print(f"⚠️ [Keep-Alive] 핑 실패: {e}")

@app.route('/ping')
def ping():
    """Keep-Alive 헬스 체크 엔드포인트"""
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()}), 200

# [백업 스케줄러] 매주 월요일 자정 0시 실행
if not scheduler.get_job('weekly_backup_job'):
    models_to_backup = [
        ('운영자 및 유저', User), ('가맹점 정보', Store), ('주문 내역', Order),
        ('포인트 트랜잭션', PointTransaction), ('고객 명단', Customer)
    ]
    scheduler.add_job(id='weekly_backup_job', func=send_daily_backup, args=(app, db, models_to_backup), trigger='cron', day_of_week='mon', hour=0, minute=0)

# [Keep-Alive] 10분마다 핑 (Render 무료 플랜 슬립 방지 - 15분 타임아웃보다 여유있게 설정)
if not scheduler.get_job('keep_alive_job'):
    scheduler.add_job(id='keep_alive_job', func=keep_alive_ping, trigger='interval', minutes=10)

scheduler.start()

# [최종] 라우트 추가 - 구글 플레이 필수 문서
@app.route('/privacy')
def privacy_page():
    return render_template('privacy.html')

@app.route('/terms')
def terms_page():
    return render_template('terms.html')

if __name__ == '__main__':
    # Render는 PORT 환경변수를 사용합니다.
    port = int(os.environ.get('PORT', 10000))
    print(f"🔥 [서버 구동] 포트 {port}번에서 MQnet Central 기동...")
    
    with app.app_context():
        try:
            db.create_all()
            
            # [자동 생성] 초기 관리자 계정이 없는 경우 생성 (테스트용)
            if not User.query.filter_by(username='admin').first():
                from werkzeug.security import generate_password_hash
                admin_user = User(
                    username='admin', 
                    password=generate_password_hash('1212'), 
                    role='admin', 
                    is_approved=True,
                    full_name='최고관리자'
                )
                db.session.add(admin_user)
                db.session.commit()
                print("👤 [계정] 초기 관리자 계정(admin/1111)이 생성되었습니다.")

            print("✅ [DB 준비 완료]")
        except Exception as e:
            print(f"⚠️ [DB 경고] {e}")

    is_render = 'RENDER' in os.environ
    debug_mode = not is_render
    socketio.run(app, debug=debug_mode, host='0.0.0.0', port=port)
