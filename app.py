# try:
#     import eventlet
#     eventlet.monkey_patch(dns=False)
# except (ImportError, AttributeError):
#     # 파이썬 3.12+ 호환성 보정 (로컬 윈도우 환경용)
#     pass

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
            # 1순위: psycopg2 시도
            import psycopg2
            if "postgresql+pg8000://" in db_url:
                db_url = db_url.replace("postgresql+pg8000://", "postgresql://", 1)
            print("🐘 [DB 엔진] psycopg2 엔진을 사용합니다.")
        except ImportError:
            # 2순위: pg8000 전환 (psycopg2 없는 환경용)
            if "postgresql+pg8000://" not in db_url:
                db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)
                db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
            print("🐘 [DB 엔진] pg8000 엔진으로 자동 전환하여 연결합니다.")

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

# [클라우드 최적화] 전역 DB 엔진 옵션 주입 (철벽 생존 모드 - NullPool)
from sqlalchemy.pool import NullPool
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'poolclass': NullPool, # 연결을 쌓아두지 않고 즉시 반납 (가장 확실한 해결책)
    'pool_pre_ping': True,
    'pool_recycle': 120,
    'pool_timeout': 180
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
        # [클라우드 배포] 부팅 속도를 위해 최소한의 테이블 확인만 수행합니다.
        print("🔍 [DB 준비] 데이터베이스 연결을 시도합니다...")
        try:
            db.create_all()
            print("✅ [DB] 연결 완료.")
        except Exception as e:
            print(f"⚠️ [DB 지연] 연결 대기 중... (첫 접속 시 재시도됨): {e}")


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
    t0 = time.time()
    user_id = session.get('user_id')
    
    # 1. 로그인 정보가 없으면 로그인 페이지로 강제 안내
    if not user_id:
        return redirect(url_for('login'))
    
    # 2. 로그인 상태라면 아래의 기존 대시보드 로직을 그대로 수행
    t1 = time.time()
    user = db.session.get(User, user_id)
    t2 = time.time()
    print(f" > [DB] User Fetch: {t2-t1:.2f}s")
    
    if not user:
        session.clear()
        return redirect(url_for('login'))
        
    role = user.role
    store_id = user.store_id
    
    # 2. Store 연결 (필요시)
    if role == 'owner' and not store_id:
        t_store_sync = time.time()
        managed_store = Store.query.filter_by(recommended_by=user.id).first()
        if managed_store:
            store_id = managed_store.id
            user.store_id = store_id
            db.session.commit()
            session['store_id'] = store_id
        print(f" > [DB] Owner Store Sync: {time.time()-t_store_sync:.2f}s")
            
    # 3. Store 목록 조회
    t3 = time.time()
    store = db.session.get(Store, store_id) if store_id else None
    stores = []
    
    if role == 'admin':
        stores = Store.query.order_by(Store.created_at.desc()).all()
    elif role == 'staff':
        try:
            stores = Store.query.filter(or_(Store.recommended_by == user_id, Store.is_public == True)).all()
        except:
            stores = Store.query.filter_by(recommended_by=user_id).all()
    t4 = time.time()
    print(f" > [DB] Store List Fetch ({role}): {t4-t3:.2f}s")
        
    # 4. Pending Users 조회
    t5 = time.time()
    users_pending = User.query.filter_by(is_approved=False).all()
    t6 = time.time()
    print(f" > [DB] Pending Users Fetch: {t6-t5:.2f}s")
    
    duration = time.time() - t0
    print(f"⏱️ [Index Load] User: {user.username}, Role: {role}, Total Duration: {duration:.2f}s")
    
    return render_template('index.html', logged_in=True, user=user, role=role, store=store, stores=stores, users_pending=users_pending)


# --- [신규] 계좌이체 안내 페이지 ---
@app.route('/<store_id>/payment_info')
def payment_info(store_id):
    store = db.session.get(Store, store_id)
    if not store:
        return "Store not found", 404
    
    # [추가] 쿼리 파라미터 지원 (금액, 메모, 주문ID)
    amount = request.args.get('amount', '')
    memo = request.args.get('memo', '')
    order_id = request.args.get('order_id', '')
    
    return render_template('bank_info.html', store=store, amount=amount, memo=memo, order_id=order_id)


# [커스텀 필터] 화폐 포맷 (10,000원 형식)
@app.template_filter('format_currency')
def format_currency_filter(value):
    if value is None: return "0원"
    return "{:,}원".format(value)

# [신규] 디지털 영수증 페이지
@app.route('/receipt/<order_id>')
def mobile_receipt(order_id):
    order = db.session.get(Order, order_id)
    if not order: return "Order not found", 404
    store = db.session.get(Store, order.store_id)
    return render_template('receipt.html', order=order, store=store)

# [API] 현금영수증 신청 정보 저장
@app.route('/api/order/<order_id>/cash_receipt', methods=['POST'])
def save_cash_receipt(order_id):
    order = db.session.get(Order, order_id)
    if not order: return jsonify({'status': 'error', 'message': 'Order not found'}), 404
    data = request.json
    order.cash_receipt_type = data.get('type')
    order.cash_receipt_number = data.get('number')
    db.session.commit()
    return jsonify({'status': 'success'})

# [테스트용] 입금 신호 시뮬레이션 API
@app.route('/api/payment/mock', methods=['POST'])
def mock_payment_trigger():
    data = request.json
    sender = data.get('sender')
    amount = int(data.get('amount', 0))
    
    # 입금 대기 중인 주문 중 이름과 금액이 일치하는 가장 최근 주문 검색
    order = Order.query.filter_by(depositor_name=sender, total_price=amount, status='pending').order_by(Order.created_at.desc()).first()
    
    if order:
        order.status = 'paid'
        order.paid_at = datetime.utcnow()
        db.session.commit()
        
        # 실시간 상태 업데이트 전송
        socketio.emit('order_update', {
            'order_id': order.id,
            'status': 'paid',
            'payment_status': 'paid'
        }, room=order.store_id)
        
        return jsonify({'status': 'success', 'message': f'Order {order.id} marked as paid.'})
    return jsonify({'status': 'error', 'message': 'Matching order not found'}), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('access_denied.html'), 403

# ---------------------------------------------------------
# [Keep-Alive] Render 슬립 방지 핑 (10분마다 자기 자신에게 요청)
# ---------------------------------------------------------
def keep_alive_ping():
    """Render 무료 플랜 서버가 잠들지 않도록 주기적으로 자기 자신에게 핑을 보냅니다.
    단순 핑이 아닌 DB 조회를 함께 수행하여 연결 상태를 확실히 점검합니다."""
    import urllib.request
    render_url = os.environ.get('RENDER_EXTERNAL_URL')
    
    # 1. DB 상태 점검 (가장 확실한 방법)
    db_ok = False
    try:
        with app.app_context():
            db.session.execute(text("SELECT 1"))
            db_ok = True
            print("🟢 [Health] 데이터베이스 연결 확인됨")
    except Exception as e:
        print(f"🚨 [오류 경보] DB 연결 실패: {str(e)}")
        # 향후 여기에 이메일 발송 또는 관리자 알림 로직 추가 가능

    # 2. Render 슬립 방지 외부 핑
    if not render_url:
        return
    try:
        ping_url = f"{render_url.rstrip('/')}/ping"
        req = urllib.request.urlopen(ping_url, timeout=10)
        print(f"✅ [Keep-Alive] 핑 성공 → {ping_url} (HTTP {req.status})")
    except Exception as e:
        print(f"⚠️ [Keep-Alive] 핑 실패: {e}")

@app.route('/ping')
def ping():
    """Keep-Alive 및 DB 점검 헬스 체크 엔드포인트"""
    db_status = "ok"
    try:
        db.session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"
        print(f"🚨 [Health Check] DB 접속 오류: {e}")
        
    return jsonify({
        'status': 'ok', 
        'db_status': db_status,
        'timestamp': datetime.utcnow().isoformat()
    }), 200 if db_status == "ok" else 500

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

# [신규] 시스템 상태 체크 API (프론트엔드 모니터링용)
@app.route('/api/health')
def health_check():
    health = {"server": "online", "db": "offline", "time": datetime.now().strftime('%H:%M:%S')}
    try:
        # DB에 아주 가벼운 쿼리를 날려 연결 확인
        db.session.execute(text('SELECT 1'))
        health["db"] = "online"
    except Exception as e:
        health["db"] = f"error: {str(e)[:50]}"
    return jsonify(health)

if __name__ == '__main__':
    # Render는 PORT 환경변수를 사용합니다.
    port = int(os.environ.get('PORT', 10000))
    print(f"🔥 [서버 구동] 포트 {port}번에서 MQnet Central 기동...")
    
    # [지연 부팅] DB 풀러 안정화를 위해 3초 대기 후 접속 시도
    import time
    time.sleep(3)
    
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
                
            # [자동 생성] 시스템 기본 설정 및 본사 계좌 정보
            config = SystemConfig.query.first()
            if not config:
                config = SystemConfig(
                    site_name='MQnet Central',
                    hq_bank='농협은행',
                    hq_account='302-0000-0000-00',
                    hq_holder='(주)MQ네트웍스'
                )
                db.session.add(config)
            
            db.session.commit()
            print("👤 [계정/설정] 초기 데이터 및 본사 정보가 준비되었습니다.")

            print("✅ [DB 준비 완료]")
        except Exception as e:
            print(f"⚠️ [DB 경고] {e}")

    is_render = 'RENDER' in os.environ
    # [최적화] Windows 로컬 + eventlet 환경에서 데드락 방지를 위해 debug 모드를 비활성화합니다.
    debug_mode = False
    
    print(f"🚀 [서버 가동] http://localhost:{port} 에서 MQnet 시스템이 활성화되었습니다.")
    socketio.run(app, debug=debug_mode, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
