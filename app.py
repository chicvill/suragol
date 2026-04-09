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
# DB 연결 설정
# ---------------------------------------------------------
if db_url:
    if db_url.startswith("postgres://") or db_url.startswith("postgresql://"):
        # [패치] psycopg2가 없는 환경(Docker/Pad)을 위해 pg8000 자동 전환
        try:
            import psycopg2
        except ImportError:
            db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)
            db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
            print("🐘 [DB 엔진] psycopg2 대신 pg8000을 사용합니다.")

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from models import db, Order, OrderItem, Waiting, Store, User, SystemConfig, TaxInvoice, ServiceRequest, Customer, PointTransaction, Attendance

# SQLALchemy 인스턴스 초기화 (모델의 db 사용)
db.init_app(app)

# [진짜 최종 마이그레이션] PostgreSQL 호환성 및 부족한 컬럼 자동 생성
with app.app_context():
    print("🔍 [DB 점검] 테이블 및 컬럼 상태를 확인합니다...")
    try:
        db.create_all()
        
        # 1. Users 테이블 컬럼 보강
        user_cols = [
            ("is_approved", "BOOLEAN DEFAULT FALSE"),
            ("agreed_at", "TIMESTAMP WITH TIME ZONE"),
            ("full_name", "VARCHAR(100)"),
            ("phone", "VARCHAR(50)"),
            ("hourly_rate", "INTEGER DEFAULT 10000"),
            ("position", "VARCHAR(50)"),
            ("work_schedule", "JSON"),
            ("contract_start", "DATE"),
            ("contract_end", "DATE")
        ]
        for col, dtype in user_cols:
            try:
                db.session.execute(text(f"ALTER TABLE users ADD COLUMN {col} {dtype}"))
                db.session.commit()
                print(f"✅ [성공] users 테이블에 {col} 컬럼이 추가되었습니다.")
            except Exception as e:
                db.session.rollback()
                if "already exists" in str(e).lower():
                    print(f"ℹ️ [알림] users.{col} 컬럼이 이미 존재합니다.")
                else:
                    print(f"⚠️ [주의] users.{col} 추가 실패: {e}")

        # 2. Stores 테이블 컬럼 보강 (개별 체크 방식)
        store_cols = [
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
            ("stats_reset_at", "TIMESTAMP WITH TIME ZONE")
        ]
        for col, dtype in store_cols:
            try:
                db.session.execute(text(f"ALTER TABLE stores ADD COLUMN {col} {dtype}"))
                db.session.commit()
                print(f"✅ [성공] stores 테이블에 {col} 컬럼이 추가되었습니다.")
            except Exception as e:
                db.session.rollback()
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    pass
                else:
                    print(f"⚠️ [주의] stores.{col} 추가 실패: {e}")

        # 3. Attendance 테이블 컨럼 보강 (예정 출돌근 시각 저장용)
        for col, dtype in [("scheduled_in", "TIMESTAMP WITH TIME ZONE"), ("scheduled_out", "TIMESTAMP WITH TIME ZONE")]:
            try:
                db.session.execute(text(f"ALTER TABLE attendance ADD COLUMN {col} {dtype}"))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                if not ("already exists" in str(e).lower() or "duplicate column" in str(e).lower()):
                    print(f"\u26a0\ufe0f [attendance.{col}] 추가 실패: {e}")

        # 4. SystemConfig 테이블 컨럼 보강
        for col, dtype in [("site_name", "VARCHAR(100) DEFAULT 'MQnet Central'"), ("maintenance_mode", "BOOLEAN DEFAULT FALSE")]:
            try:
                db.session.execute(text(f"ALTER TABLE system_configs ADD COLUMN {col} {dtype}"))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                if not ("already exists" in str(e).lower() or "duplicate column" in str(e).lower()):
                    print(f"\u26a0\ufe0f [system_configs.{col}] 추가 실패: {e}")

        # 5. [PIN 해시 마이그레이션] 기존 평문 PIN을 bcrypt 해시로 변환
        try:
            raw_stores = db.session.execute(text("SELECT id, attendance_pin FROM stores")).fetchall()
            pin_migrated = 0
            for row in raw_stores:
                pin_val = row[1] or '0000'
                if not pin_val.startswith('pbkdf2:'):
                    hashed = generate_password_hash(pin_val)
                    db.session.execute(text("UPDATE stores SET attendance_pin = :h WHERE id = :id"), {'h': hashed, 'id': row[0]})
                    pin_migrated += 1
            db.session.commit()
            if pin_migrated > 0:
                print(f"\u2705 [PIN 해시화] {pin_migrated}개 매장의 평문 PIN이 보안 해시로 변환되었습니다.")
        except Exception as e:
            db.session.rollback()
            print(f"\u26a0\ufe0f [PIN 해시화] 실패: {e}")

        # 6. 초기 계정 '대표' (Owner) 생성 로직
        default_owner = User.query.filter_by(username='대표').first()
        if not default_owner:
            new_owner = User(
                username='대표', 
                password=generate_password_hash('1111'),
                role='owner',
                full_name='통합 대표',
                is_approved=True
            )
            db.session.add(new_owner)
            db.session.commit()
            print("\ud83d\udc64 [초기화] '대표' (PW: 1111) 계정이 생성되었습니다.")

        print("🚀 [완료] 모든 데이터베이스 구조 및 초기 데이터가 동기화되었습니다.")
    except Exception as e:
        print(f"\u274c [치명적 오류] DB 초기화 실패: {e}")
        db.session.rollback()


socketio = SocketIO(app, cors_allowed_origins="*")

# MQutils Integration (Solapi SMS)
try:
    from MQutils import SolapiMessenger
except ImportError:
    class SolapiMessenger:
        def __init__(self, *args, **kwargs): pass
        def send_sms(self, to, msg): print(f"[SIM] Missing MQutils. SMS to {to}: {msg}")

# ---------------------------------------------------------
# 공통 유틸리티 및 권한 제어 (MQutils 패키지)
# ---------------------------------------------------------
from MQutils import (
    login_required, admin_required, staff_required, manager_required, owner_only_required,
    store_access_required, send_waiting_sms, check_nearby_waiting,
    format_phone, calculate_commission, get_staff_performance, send_daily_backup
)

# 템플릿 전역 변수 설정
@app.context_processor
def inject_globals():
    return {'timedelta': timedelta, 'now': datetime.now()}

# 전역 필터 등록
app.jinja_env.filters['format_phone'] = format_phone

# ---------------------------------------------------------
# 통합 관리자 센터 (MQnet Central)
# ---------------------------------------------------------

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
    
    # [추가 보정] 사장님이 특정 매장의 '담당 관리 직원'으로 등록되어 있다면, 소속 매장으로 자동 인정
    if role == 'owner' and not store_id:
        managed_store = Store.query.filter_by(recommended_by=user.id).first()
        if managed_store:
            store_id = managed_store.id
            user.store_id = store_id # DB에도 살짝 기록
            db.session.commit()
            session['store_id'] = store_id # 세션 동기화
            
    store = db.session.get(Store, store_id) if store_id else None
    
    # 최고 관리자용 전체 매장 목록
    stores = []
    if role == 'admin':
        stores = Store.query.all()
    elif role == 'staff':
        # 직원은 본인이 담당한 매장 목록 (is_public은 이제 클론 방식으로 대체 중이므로 추천 매장 우선)
        # 만약 is_public 필드가 있다면 포함, 없다면 본인 추천 매장만
        try:
            stores = Store.query.filter(or_(Store.recommended_by == user_id, Store.is_public == True)).all()
        except:
            stores = Store.query.filter_by(recommended_by=user_id).all()
        
    # 승인 대기 명단 (매니저/사장님 승인용 - 본인 매장 소속인 경우만 필터링하도록 템플릿 전달 전 최적화 가능)
    # 일단 전체를 보내되 템플릿에서 role에 따라 처리
    users_pending = User.query.filter_by(is_approved=False).all()
        
    return render_template('index.html', 
                         logged_in=True, 
                         user=user, 
                         role=role, 
                         store=store, 
                         stores=stores,
                         users_pending=users_pending)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            
            if not username or not password:
                flash("아이디와 비밀번호를 모두 입력해 주세요.")
                return redirect(url_for('login'))

            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password, password):
                # Staff 권한은 관리자 승인이 필요함
                if user.role == 'staff' and not user.is_approved:
                    flash("아직 관리자의 승인이 대기 중입니다. 승인 후 이용 가능합니다.")
                    return redirect(url_for('login'))
                
                session.permanent = True
                session.update({'user_id': user.id, 'username': user.username, 'role': user.role, 'store_id': user.store_id})
                
                # next 파라미터가 있으면 원래 페이지로 복귀, 없으면 대시보드로
                next_url = request.args.get('next') or request.form.get('next')
                if next_url and next_url.startswith('/'):
                    return redirect(next_url)
                return redirect(url_for('index'))
            
            elif user:
                flash("⚠️ 비밀번호가 올바르지 않습니다.")
            else:
                flash("🔍 등록되지 않은 아이디입니다. 아래에서 가입해 주세요.")
                
        except Exception as e:
            print(f"❌ [로그인 오류] {e}")
            flash("시스템 처리 중 오류가 발생했습니다.")
            
    return render_template('index.html', logged_in=False)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        # 역할 선택 (admin은 자가 가입 불가)
        selected_role = request.form.get('role', 'staff')
        if selected_role == 'admin': selected_role = 'staff'
        
        store_id = request.form.get('store_id', '').strip()
        
        # 유효성 검사: 점장(manager), 근로자(worker)는 업소 코드가 필수
        if selected_role in ['manager', 'worker'] and not store_id:
            flash("해당 등급으로 가입하려면 소속 업소 코드가 필요합니다.")
            return redirect(url_for('signup', role=selected_role))

        # 약관 동의 체크
        agree_profit = 'agree_profit' in request.form
        agree_privacy = 'agree_privacy' in request.form
        agree_age = 'agree_age' in request.form
        agree_not_robot = 'agree_not_robot' in request.form
        agree_labor = 'agree_labor' in request.form if selected_role == 'worker' else True

        if not all([agree_profit, agree_privacy, agree_age, agree_not_robot, agree_labor]):
            flash("모든 필수 약관에 동의하셔야 가입 신청이 가능합니다.")
            return redirect(url_for('signup', role=selected_role, store_id=store_id))

        if password != confirm_password:
            flash("비밀번호가 일치하지 않습니다.")
            return redirect(url_for('signup', role=selected_role, store_id=store_id))

        if User.query.filter_by(username=username).first():
            flash("이미 사용 중인 아이디입니다.")
            return redirect(url_for('signup', role=selected_role, store_id=store_id))

        # 근로자 전용 스케줄 및 계약 데이터 처리
        contract_start = request.form.get('contract_start')
        contract_end = request.form.get('contract_end')
        
        work_schedule = {}
        for d in ['mon','tue','wed','thu','fri','sat','sun']:
            tin = request.form.get(f'sched_{d}_in')
            tout = request.form.get(f'sched_{d}_out')
            if tin and tout:
                work_schedule[d] = {'in': tin, 'out': tout}

        role_labels = {'owner': '점주', 'manager': '점장', 'worker': '현장 근로자', 'staff': '파트너'}
        new_user = User(
            username=username,
            password=generate_password_hash(password),
            role=selected_role,
            full_name=full_name,
            phone=phone,
            store_id=store_id if store_id else None,
            is_approved=False,  # 이제 점주가 검토 후 승인
            agreed_at=datetime.utcnow(),
            contract_start=datetime.strptime(contract_start, '%Y-%m-%d').date() if contract_start else None,
            contract_end=datetime.strptime(contract_end, '%Y-%m-%d').date() if contract_end else None,
            work_schedule=work_schedule if work_schedule else None
        )
        db.session.add(new_user)
        db.session.commit()
        flash(f"✅ {role_labels.get(selected_role, '')} 가입 신청이 완료되었습니다. 관리자 승인 후 이용 가능합니다.")
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin/')
@app.route('/admin')
@login_required
def admin_dashboard():
    """종합 대시보드 대신 실적 분석 페이지로 즉시 이동"""
    return redirect(url_for('admin_performance'))

@app.route('/admin/manual/staff')
@staff_required
def staff_manual_page():
    try:
        with open('manuals/staff_manual.md', 'r', encoding='utf-8') as f:
            content = f.read()
        return render_template('admin/staff_manual_view.html', content=content)
    except: return "매뉴얼 파일을 찾을 수 없습니다.", 404

@app.route('/admin/stores', methods=['GET'])
@staff_required
def admin_stores():
    user_id = session.get('user_id')
    role = session.get('role')
    
    if role == 'admin':
        stores = Store.query.order_by(Store.created_at.desc()).all()
    else:
        # 직원은 본인이 담당한 매장 + 공개 샘플 매장 리스팅
        from sqlalchemy import or_
        stores = Store.query.filter(or_(Store.recommended_by == user_id, Store.is_public == True)).order_by(Store.created_at.desc()).all()
    return render_template('admin/stores.html', stores=stores)

@app.route('/admin/stores/add', methods=['GET', 'POST'])
@staff_required
def admin_store_add():
    role = session.get('role')
    user_id = session.get('user_id')

    if request.method == 'POST':
        sid = request.form.get('id', '').strip()
        name = request.form.get('name', '').strip()
        tables = int(request.form.get('tables', 20))
        
        # [신규] 초기 메뉴 데이터 처리
        menu_json = request.form.get('menu_data', '').strip()
        menu_data = {}
        if menu_json:
            try:
                import json
                menu_data = json.loads(menu_json)
            except: pass

        if not sid or not name:
            flash("매장 ID와 이름을 모두 입력해 주세요.")
            return redirect(url_for('admin_store_add'))
            
        if Store.query.get(sid):
            flash(f"이미 존재하거나 사용 중인 매장 ID(Slug)입니다: {sid}")
            return redirect(url_for('admin_store_add'))
            
        # 신규 매장 인스턴스 생성
        # 영업 파트너(staff)가 등록한 경우 본인을 담당 직원으로 자동 지정
        rec_by = user_id if role == 'staff' else None
        new_store = Store(id=sid, name=name, tables_count=tables, menu_data=menu_data, recommended_by=rec_by)
        db.session.add(new_store)
        db.session.commit()
        
        flash(f"🚀 새로운 가맹점[{name}]이 시스템에 정식으로 등록되어 전개되었습니다.")
        return redirect(url_for('admin_stores'))

    return render_template('admin/store_add.html')

@app.route('/admin/stores/<slug>/delete', methods=['POST'])
@staff_required
def admin_store_delete(slug):
    user_id = session.get('user_id')
    role = session.get('role')
    
    store = Store.query.get_or_404(slug)
    
    # 권한 체크: 관리자거나, 해당 매장을 등록한 담당자여야 함
    if role != 'admin' and store.recommended_by != user_id:
        flash("해당 매장에 대한 삭제 권한이 없습니다.")
        return redirect(url_for('admin_stores'))
    
    try:
        # 연관된 데이터(주문 등)는 모델의 cascade 설정에 따라 함께 처리되거나 수동 삭제 필요
        # 간단히 매장 인스턴스 삭제
        db.session.delete(store)
        db.session.commit()
        flash(f"✅ 매장 [{store.name}] 인스턴스가 성공적으로 영구 삭제되었습니다.")
    except Exception as e:
        db.session.rollback()
        flash(f"❌ 삭제 중 오류가 발생했습니다: {e}")
        
    return redirect(url_for('admin_stores'))

@app.route('/admin/stores/<slug>/config', methods=['GET', 'POST'])
@store_access_required
def admin_store_config(slug):
    store = db.session.get(Store, slug)
    user_id = session.get('user_id')
    role = session.get('role')
    user_store_id = session.get('store_id')

    # 보안 체크
    can_access = False
    if role == 'admin':
        can_access = True
    elif role == 'staff' and store.recommended_by == user_id:
        can_access = True
    elif role in ['owner', 'manager'] and slug == user_store_id:
        can_access = True
        
    if not can_access:
        flash("해당 업소에 대한 관리 권한이 없습니다.")
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # 매장 기본 정보 업데이트
        store.name = request.form.get('name')
        store.business_no = request.form.get('business_no')
        store.ceo_name = request.form.get('ceo_name')
        store.business_email = request.form.get('business_email')
        store.business_type = request.form.get('business_type')  # [추가] 업종 저장
        store.theme_color = request.form.get('theme_color', store.theme_color)
        store.contact_phone = request.form.get('contact_phone', store.contact_phone)
        store.point_ratio = float(request.form.get('point_ratio', 0))
        store.waiting_sms_no = request.form.get('waiting_sms_no', store.waiting_sms_no)
        
        # 담당 직원 및 공개 설정은 최고 관리자(Admin)만 변경 가능
        if role == 'admin':
            store.recommended_by = request.form.get('recommended_by')
            store.is_public = 'is_public' in request.form
        
        # 월 회비는 관리자나 영업 파트너만 수정 가능 (점주는 불가)
        if role in ['admin', 'staff']:
            store.monthly_fee = int(request.form.get('monthly_fee', 50000))
        
        # 메뉴 데이터 저장 (JSON 포맷)
        raw_menu = request.form.get('menu_data', '{}')
        try:
            import json
            store.menu_data = json.loads(raw_menu)
            print(f"DEBUG: [{store.id}] 메뉴판 데이터 저장 시도 -> {len(store.menu_data)} 카테고리 감지")
        except Exception as e:
            print(f"ERROR: [{store.id}] 메뉴 JSON 파싱 실패: {e}")
            
        db.session.commit()
        flash(f"매장 '{store.name}'의 모든 설정이 안전하게 저장되었습니다.")
        
        # 점주는 메인으로, 관리/직원은 목록으로 리다이렉트
        if role in ['owner', 'manager']:
            return redirect(url_for('index'))
        return redirect(url_for('admin_stores'))

    # 담당 직원 선택 목록 (Admin용)
    staffs = User.query.filter(User.role.in_(['staff', 'admin', 'owner'])).all()
    return render_template('admin/store_config.html', store=store, staffs=staffs, role=role)

@app.route('/admin/performance')
@staff_required
def admin_performance():
    user_id = session.get('user_id')
    role = session.get('role')
    
    # 분석 대상 선정
    if role == 'admin':
        staffs = User.query.filter(User.role.in_(['staff', 'admin', 'owner'])).all()
    else:
        staffs = User.query.filter_by(id=user_id).all()
    
    # 실적 데이터 합산 (MQutils 유틸리티 활용)
    performance_data = get_staff_performance(staffs, Store, Order)
    
    return render_template('admin/performance.html', data=performance_data, role=role)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """개인정보 수정 페이지 (본인 인증 필수)"""
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        data = request.json
        current_pw = data.get('current_password', '').strip()
        new_pw = data.get('new_password', '').strip()
        
        # 🛡️ 보안: 현재 비밀번호가 일치하는지 먼저 확인
        if not check_password_hash(user.password, current_pw):
            return jsonify({'status': 'error', 'message': '현재 비밀번호가 일치하지 않습니다.'}), 401
            
        # 정보 업데이트
        user.full_name = data.get('full_name', user.full_name)
        user.phone = data.get('phone', user.phone)
        
        # 새 비밀번호가 입력된 경우에만 해싱하여 저장
        if new_pw:
            user.password = generate_password_hash(new_pw)
            
        db.session.commit()
        return jsonify({'status': 'success', 'message': '개인정보가 안전하게 수정되었습니다.'})
        
    return render_template('profile.html', user=user)

@app.route('/admin/users', methods=['GET', 'POST'])
@admin_required
def admin_users():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'owner')
        sid = request.form.get('store_id')
        if User.query.filter_by(username=username).first(): flash("이미 존재하는 아이디입니다.")
        else:
            # 관리자가 직접 생성하는 계정은 즉시 승인 상태로 생성
            new_user = User(username=username, password=generate_password_hash(password), role=role, store_id=sid if sid != 'null' else None, is_approved=True)
            db.session.add(new_user)
            db.session.commit()
            flash(f"{username} 계정이 생성 및 승격되었습니다.")
        return redirect(url_for('admin_users'))
    users = User.query.all()
    stores = Store.query.all()
    return render_template('admin/users.html', users=users, stores=stores)

@app.route('/admin/users/<int:user_id>/approve', methods=['POST'])
@login_required
def admin_user_approve(user_id):
    current_role = session.get('role')
    current_user_store = session.get('store_id')
    
    user_to_approve = db.session.get(User, user_id)
    if not user_to_approve:
        flash("사용자를 찾을 수 없습니다.")
        return redirect(request.referrer or url_for('index'))

    # 권한 체크
    # 1. 최고 관리자는 모든 승인 가능
    # 2. 사장님(owner)과 점장(manager)은 본인 매장 소속이면서 파트너(staff)가 아닌 경우만 승인 가능
    can_approve = False
    if current_role == 'admin':
        can_approve = True
    elif current_role in ['owner', 'manager']:
        if user_to_approve.store_id == current_user_store and user_to_approve.role != 'staff':
            can_approve = True

    if not can_approve:
        flash("해당 사용자를 승인할 권한이 없습니다.")
        return redirect(request.referrer or url_for('index'))

    user_to_approve.is_approved = True
    db.session.commit()
    flash(f"{user_to_approve.username} 님의 가입 신청이 승인되었습니다.")
    return redirect(request.referrer or url_for('index'))

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_user_delete(user_id):
    user = db.session.get(User, user_id)
    if user:
        if user.username == session.get('username'): flash("본인 계정은 삭제할 수 없습니다.")
        else:
            db.session.delete(user)
            db.session.commit()
            flash("계정이 삭제되었습니다.")
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/update', methods=['POST'])
@admin_required
def admin_user_update(user_id):
    """승인된 사용자 정보 수정 API"""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'status': 'error', 'message': '사용자를 찾을 수 없습니다.'}), 404
    
    data = request.json
    
    # 비밀번호 (입력된 경우만 변경)
    new_pw = data.get('password', '').strip()
    if new_pw:
        user.password = generate_password_hash(new_pw)
    
    # 요일별 시간, 계약 기간
    if 'work_schedule' in data:
        user.work_schedule = data['work_schedule']
    
    if data.get('contract_start'):
        user.contract_start = datetime.strptime(data['contract_start'], '%Y-%m-%d').date()
    else:
        user.contract_start = None
        
    if data.get('contract_end'):
        user.contract_end = datetime.strptime(data['contract_end'], '%Y-%m-%d').date()
    else:
        user.contract_end = None
    
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/admin/billing')
@staff_required
def admin_billing():
    user_id = session.get('user_id')
    role = session.get('role')
    
    if role == 'admin':
        stores = Store.query.all()
    elif role == 'staff':
        # 파트너는 본인이 추천한 매장 + 공개 샘플 매장만 조회 가능
        stores = Store.query.filter(or_(Store.recommended_by == user_id, Store.is_public == True)).all()
    else:
        # 일반 점주/매니저는 본인 매장 정보만
        current_store_id = session.get('store_id')
        stores = Store.query.filter_by(id=current_store_id).all() if current_store_id else []

    unpaid = len([s for s in stores if s.payment_status == 'unpaid'])
    sus = len([s for s in stores if s.status == 'suspended'])
    
    return render_template('admin/billing.html', 
                           stores=stores, 
                           unpaid_count=unpaid, 
                           suspended_count=sus, 
                           total_stores=len(stores),
                           role=role,
                           now=datetime.utcnow())

@app.route('/partner/recruit-qr')
@staff_required
def partner_recruit_qr():
    return render_template('admin/recruit_qr.html')

@app.route('/api/admin/store/clone', methods=['POST'])
@staff_required
def api_clone_store():
    data = request.json
    source_id = data.get('source_id')
    user_id = session.get('user_id')
    
    source = db.session.get(Store, source_id)
    if not source: return jsonify({'status': 'error', 'message': '원본 매장을 찾을 수 없습니다.'}), 404
    
    # 닉네임 + 타임스탬프로 유니크한 데모 ID 생성
    import time
    demo_id = f"demo_{source_id}_{int(time.time()) % 10000}"
    
    new_store = Store(
        id=demo_id,
        name=f"[DEMO] {source.name}",
        menu_data=source.menu_data,
        theme_color=source.theme_color,
        recommended_by=user_id,
        status='active',
        # [약관준수] 원본 업소의 인적사항 및 사업자 정보는 복사하지 않음
        business_no=None,
        ceo_name=None,
        business_email=None,
        business_type=None,
        business_item=None,
        signature_owner=None,
        signature_partner=None,
        monthly_fee=50000 # 기보급형 기본값
    )
    db.session.add(new_store)
    
    # 데모 매장용 점주 계정도 자동 생성 (시연용 - 비번 1111 고정)
    demo_owner = User(
        username=f"owner_{demo_id}",
        password=generate_password_hash('1111'),
        role='owner',
        store_id=demo_id,
        is_approved=True
    )
    db.session.add(demo_owner)
    db.session.commit()
    
    return jsonify({
        'status': 'success', 
        'demo_id': demo_id, 
        'owner_id': demo_owner.username,
        'message': f'시연용 매장({demo_id})이 생성되었습니다. 점주 ID: {demo_owner.username} / PW: 1111'
    })

@app.route('/signup/new-store', methods=['GET', 'POST'])
def signup_new_store():
    # 파트너가 점주에게 보여준 QR을 통해 접속한 경우
    partner_id = request.args.get('partner_id') or request.form.get('partner_id')
    
    if request.method == 'POST':
        slug = request.form.get('slug').strip()
        name = request.form.get('name').strip()
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()
        
        # [데이터 보정] partner_id가 비어있거나 문자열일 경우를 대비해 숫자로 변환
        raw_partner_id = request.form.get('partner_id')
        try:
            partner_id_int = int(raw_partner_id) if raw_partner_id and str(raw_partner_id).isdigit() else None
        except:
            partner_id_int = None
            
        # monthly_fee 숫자 변환
        try:
            monthly_fee_int = int(request.form.get('monthly_fee', 50000))
        except:
            monthly_fee_int = 50000
        
        # 중복 체크
        if Store.query.get(slug):
            flash(f"이미 사용 중인 업소 영문 코드({slug})입니다. 다른 코드를 사용해 주세요.")
            return redirect(url_for('signup_new_store', partner_id=partner_id))
        if User.query.filter_by(username=username).first():
            flash(f"이미 존재하는 계정 아이디({username})입니다. 다른 아이디를 사용해 주세요.")
            return redirect(url_for('signup_new_store', partner_id=partner_id))

        try:
            # AI 메뉴 자동 추천 로직 적용
            business_type = request.form.get('business_type', '').strip()
            ai_menu = get_ai_recommended_menu(business_type)

            # 1. 업소 생성 (Pending 상태)
            new_store = Store(
                id=slug,
                name=name,
                menu_data=ai_menu, # [AI] 업종에 맞는 메뉴 자동 생성
                business_no=request.form.get('business_no'),
                ceo_name=request.form.get('ceo_name'),
                business_type=business_type,
                business_item=request.form.get('business_item'),
                business_email=request.form.get('business_email'),
                monthly_fee=monthly_fee_int,
                recommended_by=partner_id_int,
                signature_owner=request.form.get('sig_owner'),
                signature_partner=request.form.get('sig_partner'),
                status='pending',
                payment_status='paid',
                expires_at=datetime.utcnow() + timedelta(days=31)
            )
            db.session.add(new_store)
            db.session.flush() # [핵심] DB에 매장 정보를 먼저 밀어넣어 외래키 제약조건 충족
            
            # 2. 점주 계정 생성 (Pending 상태)
            new_owner = User(
                username=username,
                password=generate_password_hash(password),
                role='owner',
                store_id=slug,
                is_approved=False
            )
            db.session.add(new_owner)
            db.session.commit()
            
            print(f"✅ [계약 성공] 신규 가맹점({slug}) 및 점주({username}) 등록 완료!")
            
            # [추가] 가계약 완료 후 자동 로그인 처리 (상세 설정 즉시 진입용)
            session['user_id'] = new_owner.id
            session['username'] = new_owner.username
            session['role'] = new_owner.role
            session['store_id'] = new_owner.store_id
            
            flash("🎉 가계약이 체결되었습니다! 매장의 메뉴와 상세 정보를 설정해 주세요.")
            return redirect(url_for('admin_store_config', slug=slug))

        except Exception as e:
            db.session.rollback()
            print(f"❌ [계약 실패] 오류 발생: {e}")
            flash(f"가계약 체결 중 오류가 발생했습니다: {str(e)}")
            return redirect(url_for('signup_new_store', partner_id=partner_id))

    return render_template('signup/new_store.html', partner_id=partner_id)

@app.route('/admin/stores/setup/<slug>', methods=['GET', 'POST'])
@login_required
def admin_store_setup(slug):
    store = db.session.get(Store, slug)
    if not store: return "Store not found", 404
    
    if request.method == 'POST':
        store.theme_color = request.form.get('theme_color')
        store.contact_phone = request.form.get('contact_phone')
        store.point_ratio = float(request.form.get('point_ratio', 0))
        store.waiting_sms_no = request.form.get('waiting_sms_no')
        db.session.commit()
        
        flash("매장 맞춤 설정이 저장되었습니다. 어드민이 확인 후 원격 승인 시 운영이 개시됩니다.")
        return redirect(url_for('index'))
        
    return render_template('admin/store_setup.html', store=store)

@app.route('/admin/billing/payouts')
@admin_required
def admin_payout_list():
    # 정산 대상에 관리자(admin) 및 사장님(owner)도 포함하도록 수정
    partners = User.query.filter(User.role.in_(['staff', 'admin', 'owner']), User.is_approved == True).all()
    payout_data = []
    now = datetime.utcnow()
    
    for p in partners:
        # 해당 파트너가 담당하는 매장들 조회
        stores = Store.query.filter_by(recommended_by=p.id).all()
        total_payout = 0
        billable_stores_count = 0
        
        for s in stores:
            if s.payment_status == 'paid':
                # 가입 후 2개월(60일) 이상 경과한 매장만 정산 대상 (가입월 + 무료지원월 제외)
                delta = now - s.created_at
                total_months = delta.days // 30
                if total_months >= 2:
                    total_payout += (s.monthly_fee or 50000)
                    billable_stores_count += 1
        
        # 정산할 금액이 있거나 매장이 있는 경우 리스트 업
        if total_payout > 0 or len(stores) > 0:
            payout_data.append({
                'name': p.full_name or p.username,
                'phone': p.phone or '연락처 미기재',
                'amount': total_payout,
                'store_count': len(stores),
                'billable_count': billable_stores_count
            })
            
    # 매월 25일 기준으로 표시
    display_date = now.strftime('%Y년 %m월 25일')
    return render_template('admin/payout_print.html', payout_data=payout_data, date=display_date)

@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    config = SystemConfig.query.first()
    if request.method == 'POST':
        if not config:
            config = SystemConfig()
            db.session.add(config)
        config.site_name = request.form.get('site_name', 'MQnet Central')
        config.maintenance_mode = 'maintenance_mode' in request.form
        db.session.commit()
        flash("시스템 설정이 저장되었습니다.")
        return redirect(url_for('admin_settings'))
    return render_template('admin/settings.html', config=config)

@app.route('/api/admin/billing/toggle', methods=['POST'])
@admin_required
def api_billing_toggle():
    data = request.json
    sid = data.get('store_id')
    store = db.session.get(Store, sid)
    if store:
        store.payment_status = 'paid' if store.payment_status == 'unpaid' else 'unpaid'
        if store.payment_status == 'paid':
            now = datetime.utcnow()
            if not store.expires_at or store.expires_at < now: store.expires_at = now + timedelta(days=30)
        db.session.commit()
        return jsonify({'status': 'success', 'new_status': store.payment_status})
    return jsonify({'status': 'error'}), 404

@app.route('/api/admin/store/status-toggle', methods=['POST'])
@admin_required
def api_status_toggle():
    data = request.json
    sid = data.get('store_id')
    store = db.session.get(Store, sid)
    if store:
        # 'active'면 'unregistered'로, 그 외엔 'active'로 토글
        store.status = 'unregistered' if store.status == 'active' else 'active'
        db.session.commit()
        return jsonify({'status': 'success', 'new_status': store.status})
    return jsonify({'status': 'error'}), 404

@app.route('/api/admin/upload', methods=['POST'])
@staff_required
def api_upload_image():
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    file = request.files.get('file')
    if not file: return jsonify({'error': 'No file'}), 400
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f'허용되지 않는 파일 형식입니다. ({ext}). 허용: {ALLOWED_EXTENSIONS}'}), 400
    filename = str(uuid.uuid4()) + '.' + ext  # 원본 파일명을 UUID로 완전 대체 (Path Traversal 방지)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return jsonify({'status': 'success', 'url': f'/static/images/{filename}'})
# ---------------------------------------------------------
# 매장별 서비스 라우트 (와일드카드 처리를 위해 맨 뒤로 배치)
# ---------------------------------------------------------

@app.route('/<slug>')
def store_index(slug):
    # 브라우저의 아이콘 요청(favicon.ico)은 무시
    if slug == 'favicon.ico': return "", 204
    
    # 이모지는 윈도우 환경에서 인코딩 에러를 유발할 수 있어 제거했습니다.
    print(f"--- [Domain Request] Accessing Slug: {slug} ---")
    store = db.session.get(Store, slug)
    if not store:
        print(f"--- [Error] Store '{slug}' not found in DB. Redirecting to portal. ---")
        return redirect(url_for('index'))
    
    try: 
        # 고객은 사장님 포털이 아닌, 주문판(customer_view)으로 즉시 유도합니다.
        return redirect(url_for('customer_view', slug=slug, table_id=1))
    except Exception as e:
        print(f"--- [Redirect Error] Falling back to manual URL: {e} ---")
        return redirect(f"/{slug}/customer/1")

@app.route('/<slug>/customer/<int:table_id>')
def customer_view(slug, table_id):
    store = Store.query.get_or_404(slug)
    
    # [방어 로직] 메뉴 데이터가 없거나 완전히 비어있는 경우 자동 복구 및 샘플 생성
    if not store.menu_data or len(store.menu_data) == 0:
        store.menu_data = {"✨ 추천 메뉴": []}
        db.session.commit()
        print(f"🛠 [복구] {slug} 매장에 기본 카테고리를 생성했습니다.")
        
    if 'uid' not in session:
        # uuid4를 사용하여 900개 충돌 문제 해결 (기존 randint(100,999)는 충돌 위험 높음)
        session['uid'] = str(uuid.uuid4())[:12]
        session.modified = True
    return render_template('customer.html', store=store, table_id=table_id, session_id=session['uid'])

@app.route('/<slug>/counter')
@store_access_required
def counter_view(slug):
    store = db.session.get(Store, slug)
    if not store: return redirect(url_for('index'))
    # [AI] 매장 운영 인사이트 생성
    insight = get_ai_operation_insight(store)
    return render_template('counter.html', store=store, ai_insight=insight)

@app.route('/api/<slug>/ai-insight')
@store_access_required
def api_ai_insight(slug):
    store = db.session.get(Store, slug)
    if not store: return jsonify({'error': 'Not found'}), 404
    return jsonify({
        'status': 'success',
        'insight': get_ai_operation_insight(store)
    })

@app.route('/api/ai-menu-template')
@login_required
def api_ai_menu_template():
    # 쿼리 파라미터로 받은 업종(type)을 기반으로 추천 메뉴 반환
    biz_type = request.args.get('type', '')
    return jsonify(get_ai_recommended_menu(biz_type))

@app.route('/<slug>/kitchen')
@store_access_required
def kitchen_view(slug):
    store = db.session.get(Store, slug)
    if not store: return redirect(url_for('index'))
    return render_template('kitchen.html', store=store)

@app.route('/<slug>/qr-print')
@store_access_required
def qr_print_view(slug):
    store = db.session.get(Store, slug)
    if not store: return "매장을 찾을 수 없습니다.", 404
    
    # [핵심] QR용 베이스 URL 자동 추출 (localhost일 경우 운영 서버 주소로 강제 전환)
    current_url = request.host_url.rstrip('/')
    if 'localhost' in current_url or '127.0.0.1' in current_url:
        current_url = 'https://free.chicvill.store'
    else:
        current_url = current_url.replace('http://', 'https://')
        
    return render_template('qr_print.html', store=store, current_url=current_url)

@app.route('/admin/stores/<slug>/qr-print')
@staff_required
def admin_qr_print_view(slug):
    store = db.session.get(Store, slug)
    if not store: return "매장을 찾을 수 없습니다.", 404
    
    # [핵심] 현재 접속 중인 도메인을 자동으로 감지하여 QR 주소로 사용 (localhost일 경우 운영 서버 주소로 강제 전환)
    current_url = request.host_url.rstrip('/')
    if 'localhost' in current_url or '127.0.0.1' in current_url:
        current_url = 'https://free.chicvill.store'
    else:
        current_url = current_url.replace('http://', 'https://')
        
    return render_template('qr_print.html', store=store, current_url=current_url)



@app.route('/<slug>/display')
def display_view(slug):
    store = db.session.get(Store, slug)
    if not store: return redirect(url_for('store_selection'))
    return render_template('display.html', store=store)

@app.route('/<slug>/stats')
@store_access_required
def stats_view(slug):
    store = db.session.get(Store, slug)
    if not store: return redirect(url_for('store_selection'))
    return render_template('stats.html', store=store)

@app.route('/api/<slug>/stats')
@store_access_required
def api_get_stats(slug):
    period = request.args.get('period', 'today')
    # [수정] UTC 기준으로 통일 (기존 datetime.now()는 KST로 저장된 UTC 데이터와 9시간 시차 발생)
    now = datetime.utcnow()
    
    if period == 'week':
        start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'month':
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == 'year':
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # [수정] 통계 리셋 기준점 반영 (실제 데이터 변조 없이 기준 시각으로 필터링)
    store = db.session.get(Store, slug)
    if store and store.stats_reset_at:
        start_date = max(start_date, store.stats_reset_at)
    

    # 1. 기간 총 매출
    total_sales = db.session.query(func.sum(Order.total_price))\
        .filter(Order.store_id == slug, Order.status == 'paid', Order.paid_at >= start_date)\
        .scalar() or 0
        
    # 2. 인기 메뉴 TOP 5
    best_items = db.session.query(OrderItem.name, func.sum(OrderItem.quantity).label('total_count'))\
        .join(Order, Order.id == OrderItem.order_id)\
        .filter(Order.store_id == slug, Order.status == 'paid', Order.paid_at >= start_date)\
        .group_by(OrderItem.name)\
        .order_by(desc('total_count'))\
        .limit(5).all()
    
    best_menu = [{'name': name, 'count': int(count)} for name, count in best_items]
    
    return jsonify({
        'sales': int(total_sales),
        'best_menu': best_menu,
        'period': period,
        'start_date': start_date.strftime('%Y-%m-%d')
    })

@app.route('/api/<slug>/customers')
@store_access_required
def api_get_store_customers(slug):
    custs = Customer.query.filter_by(store_id=slug).order_by(desc(Customer.total_spent)).all()
    return jsonify([{
        'phone': c.phone,
        'visit_count': c.visit_count,
        'total_spent': c.total_spent,
        'points': c.points
    } for c in custs])






@app.route('/api/<slug>/stats/reset', methods=['POST'])
@store_access_required
def api_reset_stats(slug):
    """[수정] 실제 데이터(paid_at)를 변조하지 않고 리셋 기준시각을 저장하는 방식화"""
    store = db.session.get(Store, slug)
    if not store:
        return jsonify({'status': 'error', 'message': '매장을 찾을 수 없습니다.'}), 404
    store.stats_reset_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'status': 'success', 'reset_at': store.stats_reset_at.isoformat()})

@app.route('/<slug>/waiting')
def waiting_view(slug):
    store = db.session.get(Store, slug)
    return render_template('waiting.html', store=store)

@app.route('/<slug>/manual')
def store_manual_view(slug):
    store = db.session.get(Store, slug)
    return render_template('admin/visual_manual.html', store=store)

@app.route('/api/<slug>/service_request', methods=['POST'])
def api_create_service_request(slug):
    data = request.json
    content = data.get('content')
    table_id = data.get('table_id')
    if not content or not table_id: return jsonify({'error': 'Missing data'}), 400
    new_req = ServiceRequest(store_id=slug, table_id=table_id, content=content)
    db.session.add(new_req)
    db.session.commit()
    socketio.emit('new_service_request', new_req.to_dict(), room=slug)
    return jsonify({'status': 'success', 'request': new_req.to_dict()})

@app.route('/api/<slug>/service_requests')
@store_access_required
def api_get_service_requests(slug):
    reqs = ServiceRequest.query.filter_by(store_id=slug, status='pending').order_by(ServiceRequest.created_at.desc()).all()
    return jsonify([r.to_dict() for r in reqs])

@app.route('/api/<slug>/orders')
def api_get_active_orders(slug):
    """현재 결제되지 않은(식사 중이거나 조리 중인) 모든 주문 내역을 반환합니다."""
    orders = Order.query.filter(Order.store_id == slug, Order.status != 'paid').all()
    return jsonify([o.to_dict() for o in orders])


@app.route('/api/<slug>/service_request/<int:req_id>/complete', methods=['POST'])
@store_access_required
def api_complete_service_request(slug, req_id):
    req = db.session.get(ServiceRequest, req_id)
    if req and req.store_id == slug:
        req.status = 'completed'
        db.session.commit()
        socketio.emit('service_request_completed', {'id': req_id}, room=slug)
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Not found'}), 404

# ---------------------------------------------------------
# 직원 근태 및 출퇴근 관리 API
# ---------------------------------------------------------

@app.route('/api/<slug>/attendance/check-in', methods=['POST'])
@login_required
def api_staff_check_in(slug):
    user_id = session.get('user_id')
    role = session.get('role')
    user = db.session.get(User, user_id)
    
    # [권한 체크] 현장 근로자(worker) 및 점장(manager)만 출퇴근 가능
    if role not in ['worker', 'manager']:
        return jsonify({'status': 'error', 'message': '현장 근로자 및 점장 계정 전용 기능입니다.'}), 403
    
    # [소속 체크]
    if not user or not user.store_id or user.store_id != slug:
        return jsonify({'status': 'error', 'message': '해당 매장에 등록되지 않은 근로자입니다.'}), 403

    # [계약 기간 체크]
    # 서버 시간과 상권 현지 시간(KST) 동기화
    kst = timezone(timedelta(hours=9))
    now_full = datetime.now(kst)
    today_date = now_full.date()
    if user.contract_start and today_date < user.contract_start:
        return jsonify({'status': 'error', 'message': f'근무 시작 전입니다. (시작일: {user.contract_start})'}), 400
    if user.contract_end and today_date > user.contract_end:
        return jsonify({'status': 'error', 'message': f'계약 기간이 종료되었습니다. (종료일: {user.contract_end})'}), 400

    # [요일별 시간 체크]
    days_map = {0: 'mon', 1: 'tue', 2: 'wed', 3: 'thu', 4: 'fri', 5: 'sat', 6: 'sun'}
    today_key = days_map[now_full.weekday()]
    
    if not user.work_schedule or today_key not in user.work_schedule:
        return jsonify({'status': 'error', 'message': '오늘은 근무일이 아닙니다.'}), 400
        
    sched = user.work_schedule[today_key]
    in_time_str = sched.get('in')
    if not in_time_str:
        return jsonify({'status': 'error', 'message': '정해진 출근 시간이 없습니다.'}), 400
    
    # 정해진 시간을 오늘 날짜의 datetime으로 변환 (naive)
    target_in = datetime.strptime(f"{today_date} {in_time_str}", "%Y-%m-%d %H:%M")
    
    # 10분 범위 체크 (naive 끼리 비교) - 약관 반영
    now_naive = now_full.replace(tzinfo=None)
    diff = abs((now_naive - target_in).total_seconds())
    if diff > 600: # 10분 = 600초
        return jsonify({'status': 'error', 'message': f'출근 가능 시간이 아닙니다. (정해진 시간: {in_time_str} 전후 10분 이내 가능)'}), 400

    # 이미 출근 중인지 확인
    existing = Attendance.query.filter(Attendance.user_id==user_id, Attendance.store_id==slug, Attendance.status=='working').first()
    if existing:
        return jsonify({'status': 'error', 'message': '이미 업무 진행 중입니다.'}), 400
    
    # [자동 승인] 정해진 시간에 출근한 것으로 기록
    # DB는 UTC로 저장하므로 KST(target_in)를 UTC로 변환하여 저장
    target_in_utc = target_in - timedelta(hours=9)
    
    new_att = Attendance(
        user_id=user_id, 
        store_id=slug, 
        check_in_at=target_in_utc, 
        status='working'
    )
    db.session.add(new_att)
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': f'출근 처리되었습니다. (기록시간: {in_time_str})'})

@app.route('/api/<slug>/attendance/check-out', methods=['POST'])
@login_required
def api_staff_check_out(slug):
    user_id = session.get('user_id')
    role = session.get('role')
    user = db.session.get(User, user_id)
    
    if role not in ['worker', 'manager']:
        return jsonify({'status': 'error', 'message': '현장 근로자 및 점장 계정 전용 기능입니다.'}), 403

    att = Attendance.query.filter_by(user_id=user_id, store_id=slug, status='working').first()
    if not att:
        return jsonify({'status': 'error', 'message': '업무 중인 상태가 아닙니다.'}), 400
    
    # [요일별 시간 체크]
    kst = timezone(timedelta(hours=9))
    now_full = datetime.now(kst)
    today_date = now_full.date()
    days_map = {0: 'mon', 1: 'tue', 2: 'wed', 3: 'thu', 4: 'fri', 5: 'sat', 6: 'sun'}
    today_key = days_map[now_full.weekday()]
    
    if not user.work_schedule or today_key not in user.work_schedule:
        return jsonify({'status': 'error', 'message': '오늘은 근무 정해진 퇴근 시간이 없습니다.'}), 400
        
    sched = user.work_schedule[today_key]
    out_time_str = sched.get('out')
    if not out_time_str:
        return jsonify({'status': 'error', 'message': '정해진 퇴근 시간이 없습니다.'}), 400
    
    # 정해진 시간을 오늘 날짜의 datetime으로 변환 (naive)
    target_out = datetime.strptime(f"{today_date} {out_time_str}", "%Y-%m-%d %H:%M")
    
    # 10분 범위 체크 (naive 끼리 비교) - 약관 반영
    now_naive = now_full.replace(tzinfo=None)
    diff = abs((now_naive - target_out).total_seconds())
    if diff > 600: # 10분 = 600초
        return jsonify({'status': 'error', 'message': f'퇴근 가능 시간이 아닙니다. (정해진 시간: {out_time_str} 전후 10분 이내 가능)'}), 400

    # [자동 승인] 정해진 시간에 퇴근한 것으로 기록
    # DB는 UTC로 저장하므로 KST(target_out)를 UTC로 변환하여 저장
    target_out_utc = target_out - timedelta(hours=9)
    att.check_out_at = target_out_utc
    duration = att.check_out_at - att.check_in_at
    att.total_minutes = max(0, int(duration.total_seconds() / 60))
    att.status = 'completed'
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': f'퇴근 처리되었습니다. (기록시간: {out_time_str})'})

@app.route('/api/<slug>/attendance/pending', methods=['GET'])
@login_required
def api_get_pending_attendance(slug):
    if session.get('role') not in ['admin', 'owner']: return jsonify({'error': 'Forbidden'}), 403
    
    pending_list = Attendance.query.filter(Attendance.store_id==slug, Attendance.status.in_(['pending_in', 'pending_out'])).all()
    data = []
    for att in pending_list:
        data.append({
            'id': att.id,
            'user_name': att.user.full_name or att.user.username,
            'type': '출근' if att.status == 'pending_in' else '퇴근',
            'time': att.check_in_at.strftime('%H:%M') if att.status == 'pending_in' else (att.check_out_at.strftime('%H:%M') if att.check_out_at else '-')
        })
    return jsonify(data)

@app.route('/api/<slug>/attendance/bulk-approve', methods=['POST'])
@login_required
def api_bulk_approve_attendance(slug):
    if session.get('role') not in ['admin', 'owner']: return jsonify({'error': 'Forbidden'}), 403
    
    data = request.json
    pin = data.get('pin')
    selected_ids = data.get('ids', []) # 사장님이 체크한 ID 리스트
    
    store = db.session.get(Store, slug)
    if not store or not check_password_hash(store.attendance_pin, pin):
        return jsonify({'status': 'error', 'message': '보안 코드가 일치하지 않습니다.'}), 400
    
    # 사장님이 선택한 ID들만 필터링하여 승인
    pending_list = Attendance.query.filter(Attendance.id.in_(selected_ids)).all()
    
    count = 0
    for att in pending_list:
        if att.status == 'pending_in':
            # [수정] 승인 시각(now) 대신 예정 출근 시각(scheduled_in) 기준으로 기록
            att.check_in_at = att.scheduled_in or att.check_in_at
            att.status = 'working'
            count += 1
        elif att.status == 'pending_out':
            # [수정] 승인 시각(now) 대신 예정 퇴근 시각(scheduled_out) 기준으로 기록
            att.check_out_at = att.scheduled_out or att.check_out_at
            diff = att.check_out_at - att.check_in_at
            att.total_minutes = max(0, int(diff.total_seconds() / 60))
            att.status = 'completed'
            count += 1
            
    db.session.commit()
    socketio.emit('attendance_approved', {'bulk': True}, room=slug)
    return jsonify({'status': 'success', 'count': count})

@app.route('/api/<slug>/attendance/approve', methods=['POST'])
@login_required
def api_approve_attendance(slug):
    if session.get('role') not in ['admin', 'owner']: return jsonify({'error': 'Forbidden'}), 403
    
    data = request.json
    att_id = data.get('id')
    pin = data.get('pin')
    
    store = db.session.get(Store, slug)
    if not store or not check_password_hash(store.attendance_pin, pin):
        return jsonify({'status': 'error', 'message': '보안 코드가 일치하지 않습니다.'}), 400
        
    att = db.session.get(Attendance, att_id)
    if not att: return jsonify({'error': 'Not found'}), 404
    
    if att.status == 'pending_in':
        # [수정] 승인 시각 대신 예정 시각 기준으로 기록
        att.check_in_at = att.scheduled_in or att.check_in_at
        att.status = 'working'
    elif att.status == 'pending_out':
        att.check_out_at = att.scheduled_out or att.check_out_at
        diff = att.check_out_at - att.check_in_at
        att.total_minutes = max(0, int(diff.total_seconds() / 60))
        att.status = 'completed'
    
    db.session.commit()
    # 직원 화면 업데이트용 신호
    socketio.emit('attendance_approved', {'id': att_id, 'user_id': att.user_id}, room=slug)
    return jsonify({'status': 'success'})

@app.route('/api/<slug>/attendance/update-pin', methods=['POST'])
@login_required
def api_update_attendance_pin(slug):
    if session.get('role') not in ['admin', 'owner']: return jsonify({'error': 'Forbidden'}), 403
    
    data = request.json
    old_pin = data.get('old_pin')
    new_pin = data.get('new_pin')
    
    store = db.session.get(Store, slug)
    if not store: return jsonify({'error': 'Not found'}), 404
    
    # [수정] 현재 PIN 해시 보안 비교
    if not check_password_hash(store.attendance_pin, old_pin):
        return jsonify({'status': 'error', 'message': '현재 보안 코드가 일치하지 않아 변경할 수 없습니다.'}), 400
        
    if not new_pin or len(new_pin) != 4 or not new_pin.isdigit():
        return jsonify({'status': 'error', 'message': '새 보안 코드는 4자리 숫자여야 합니다.'}), 400
        
    # [수정] 새 PIN을 bcrypt 해시로 저장
    store.attendance_pin = generate_password_hash(new_pin)
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/<slug>/attendance/staff-status')
@login_required
def api_get_attendance_status(slug):
    user_id = session.get('user_id')
    user = db.session.get(User, user_id)
    # [권한 체크] 현장 근로자(worker)만 이 화면 사용 가능
    if user.role != 'worker':
        return jsonify({'status': 'forbidden', 'message': '현장 근로자 계정 전용 기능입니다.'})

    att = Attendance.query.filter(Attendance.user_id==user_id, Attendance.store_id==slug, Attendance.status.in_(['working', 'pending_in', 'pending_out'])).first()
    
    # [급여 산출] 이번 달 1일부터 현재까지 정산된 금액
    now = datetime.utcnow()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total_mins = db.session.query(func.sum(Attendance.total_minutes))\
        .filter(Attendance.user_id == user_id, Attendance.store_id == slug, Attendance.check_in_at >= start_of_month)\
        .scalar() or 0
    current_wage = int((total_mins / 60) * (user.hourly_rate or 0))

    return jsonify({
        'status': att.status if att else 'none',
        'is_working': (att and att.status == 'working'),
        'current_wage': current_wage,
        'check_in_at': att.check_in_at.isoformat() if (att and att.check_in_at) else None
    })

@app.route('/<slug>/attendance')
@login_required
def staff_attendance_view(slug):
    # 영업 파트너(staff)가 접근할 경우 리다이렉트 처리
    if session.get('role') == 'staff':
        flash("영업 파트너는 근로시간 정산 대상이 아닙니다.")
        return redirect(url_for('admin_dashboard'))
    store = db.session.get(Store, slug)
    return render_template('staff_attendance.html', store=store)

@app.route('/admin/staff')
@login_required
def admin_staff_mgmt():
    user_id = session.get('user_id')
    role = session.get('role')
    user_store_id = session.get('store_id')
    
    if role not in ['admin', 'owner', 'staff', 'manager']:
        return render_template('access_denied.html')
    
    # [임금 수정 권한] 오직 어드민과 사장님(owner)만 시급 수정 가능
    can_edit_wage = (role in ['admin', 'owner'])
    
    # 영업 파트너(staff)는 본인 담당 매장만 접근 가능하도록 필터링
    if role == 'staff':
        managed_stores = Store.query.filter_by(recommended_by=user_id).all()
        managed_ids = [s.id for s in managed_stores]
        selected_slug = request.args.get('slug') or (managed_ids[0] if managed_ids else None)
        if selected_slug not in managed_ids:
            flash("해당 매장에 대한 관리 권한이 없습니다.")
            return redirect(url_for('index'))
        stores = managed_stores
    elif role == 'admin':
        stores = Store.query.all()
        selected_slug = request.args.get('slug') or (stores[0].id if stores else None)
    else:
        selected_slug = user_store_id
        stores = Store.query.filter_by(id=selected_slug).all()
        
    store = db.session.get(Store, selected_slug) if selected_slug else None
    
    # [기간 설정] 기본값: 이번 달 1일부터 오늘까지
    now = datetime.now()
    start_str = request.args.get('start_date') or now.replace(day=1).strftime('%Y-%m-%d')
    end_str = request.args.get('end_date') or now.strftime('%Y-%m-%d')
    start_dt = datetime.strptime(start_str, '%Y-%m-%d').replace(hour=0, minute=0, second=0)
    end_dt = datetime.strptime(end_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

    # 1. 현장 근로자(worker) 정밀 리포트 (일자별 내역 포함)
    workers = User.query.filter_by(store_id=selected_slug, role='worker').all()
    worker_reports = []
    for w in workers:
        # 해당 기간의 모든 완료된 근태 기록 조회
        attendances = Attendance.query.filter(
            Attendance.user_id == w.id, 
            Attendance.store_id == selected_slug,
            Attendance.check_in_at >= start_dt,
            Attendance.check_in_at <= end_dt,
            Attendance.status == 'completed'
        ).order_by(Attendance.check_in_at).all()
        
        total_mins = sum((a.total_minutes or 0) for a in attendances)
        wage = int((total_mins / 60) * (w.hourly_rate or 0))
        
        # 일별 합산 내역 생성
        daily_details = []
        for att in attendances:
            if att.check_in_at:
                daily_details.append({
                    'date': att.check_in_at.strftime('%m-%d'),
                    'start': att.check_in_at.strftime('%H:%M'),
                    'end': att.check_out_at.strftime('%H:%M') if att.check_out_at else '-',
                    'mins': att.total_minutes or 0
                })

        worker_reports.append({
            'user': w,
            'minutes': total_mins,
            'hours': round(total_mins / 60, 1),
            'expected_wage': wage,
            'details': daily_details
        })
    
    # 2. 영업 파트너(staff) 수당 리포트 (매출 기반)
    partners = User.query.filter_by(store_id=selected_slug, role='staff').all()
    partner_reports = []
    if store:
        # 해당 기간의 총 매출(실제 결제 완료된 주문 기준)
        total_sales = db.session.query(func.sum(Order.total_price))\
            .filter(Order.store_id == selected_slug, Order.created_at >= start_dt, Order.created_at <= end_dt, Order.status == 'paid')\
            .scalar() or 0
        
        # 사장님 정책: 매출의 10%를 해당 가맹점을 관리하는 파트너들에게 지급하는 구조라면
        commission_pool = int(total_sales * 0.1)
        
        for p in partners:
            partner_reports.append({
                'user': p,
                'period_sales': total_sales,
                'commission': commission_pool # 파트너별 정교한 분배 로직이 필요할 경우 여기서 수정
            })
        
    return render_template('admin/staff_mgmt.html', stores=stores, selected_slug=selected_slug, 
                           worker_reports=worker_reports, partner_reports=partner_reports, 
                           store=store, start_date=start_str, end_date=end_str, now=now,
                           can_edit_wage=can_edit_wage)

@app.route('/api/staff/<int:user_id>/update', methods=['POST'])
@owner_only_required # 사장님 전용 권한 데코레이터 적용
def api_update_staff_wage(user_id):
    
    data = request.json
    user = db.session.get(User, user_id)
    if user:
        user.hourly_rate = data.get('hourly_rate', user.hourly_rate)
        user.position = data.get('position', user.position)
        user.role = data.get('role', user.role)
        user.phone = data.get('phone', user.phone)
        user.full_name = data.get('full_name', user.full_name) # 성명 변경도 가능하게 추가
        
        if 'work_schedule' in data:
            user.work_schedule = data['work_schedule']
            
        if data.get('contract_start'):
            user.contract_start = datetime.strptime(data['contract_start'], '%Y-%m-%d').date()
        else:
            user.contract_start = None

        if data.get('contract_end'):
            user.contract_end = datetime.strptime(data['contract_end'], '%Y-%m-%d').date()
        else:
            user.contract_end = None

        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'error': 'User not found'}), 404
# ---------------------------------------------------------
# 웨이팅(예약) 시스템 API
# ---------------------------------------------------------

@app.route('/api/<slug>/waiting', methods=['POST'])
def api_create_waiting(slug):
    data = request.json
    phone = data.get('phone', '010-0000-0000')
    people = int(data.get('people', 1))
    
    # [수정] 취소/입장 제외한 실제 대기 중인 팀 수 기반으로 번호 부여 (기존: 전체 카운트 → 번호 급증 문제)
    now_local = datetime.now()
    today_start = datetime(now_local.year, now_local.month, now_local.day)
    today_count = Waiting.query.filter_by(store_id=slug).filter(
        Waiting.created_at >= today_start
    ).count()  # 오늘 접수된 전체 수 (연번 부여용)
    
    new_wait = Waiting(store_id=slug, phone=phone, people=people, waiting_no=today_count+1)
    db.session.add(new_wait)
    db.session.commit()
    
    socketio.emit('waiting_update', room=slug)

    # 신규 등록 후에도 3팀 체크 (혹시 바로 3번째일 수도 있음)
    check_nearby_waiting(app, slug)
    
    return jsonify({'status': 'success', 'wait_id': new_wait.id})

@app.route('/api/<slug>/waiting/list')
@store_access_required
def api_get_waiting_list(slug):
    waits = Waiting.query.filter_by(store_id=slug, status='waiting').order_by(Waiting.created_at.asc()).all()
    return jsonify([w.to_dict() for w in waits])

@app.route('/api/<slug>/waiting/status/<int:wait_id>')
def api_get_waiting_status(slug, wait_id):
    w = db.session.get(Waiting, wait_id)
    if not w: return jsonify({'status': 'not_found'})
    
    # 내 앞에 몇 팀 있는지 계산
    rank = Waiting.query.filter_by(store_id=slug, status='waiting').filter(Waiting.created_at < w.created_at).count()
    
    res = w.to_dict()
    res['rank'] = rank
    res['created_at_fixed'] = w.created_at.strftime('%H:%M')
    return jsonify(res)


@app.route('/api/<slug>/waiting/notify/<int:wait_id>', methods=['POST'])
@store_access_required
def api_notify_waiting_manual(slug, wait_id):
    """수동으로 근사 알림(상황별 알림)을 다시 보냅니다."""
    w = db.session.get(Waiting, wait_id)
    if w and w.store_id == slug:
        # 수동 발송 시에도 백그라운드 스레드로 발송
        threading.Thread(target=send_waiting_sms, args=(app, wait_id, 'nearby')).start()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': '대기 정보를 찾을 수 없습니다.'}), 404

@app.route('/api/<slug>/waiting/enter/<int:wait_id>', methods=['POST'])
@store_access_required
def api_enter_waiting(slug, wait_id):
    w = db.session.get(Waiting, wait_id)
    if w and w.store_id == slug:
        w.status = 'entered'
        db.session.commit()
        
        # 고객 화면 실시간 업데이트 신호
        socketio.emit('waiting_status_update', {'wait_id': wait_id, 'status': 'entered'}, room=slug)
        socketio.emit('waiting_update', room=slug)
        
        # 입장 알림 발송 (백그라운드)
        threading.Thread(target=send_waiting_sms, args=(app, wait_id, 'enter')).start()
        
        # 대기열이 한 칸씩 당겨졌으므로 새로운 상위 고객 체크 (자동 알림)
        check_nearby_waiting(app, slug)
            
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Not found', 'message': '대기 정보를 찾을 수 없습니다.'}), 404

@app.route('/api/<slug>/waiting/cancel/<int:wait_id>', methods=['POST'])
def api_cancel_waiting(slug, wait_id):
    """대기 취소 처리를 수행합니다 (고객 본인 또는 직원)."""
    w = db.session.get(Waiting, wait_id)
    if w and w.store_id == slug:
        w.status = 'canceled'
        db.session.commit()
        
        # 취소 시에도 당연히 대기열이 당겨지므로 전체 업데이트 및 다음 근접팀 알림 체크
        socketio.emit('waiting_status_update', {'wait_id': wait_id, 'status': 'canceled'}, room=slug)
        socketio.emit('waiting_update', room=slug)
        
        # 새로운 상위 고객 체크하여 알림 발송
        check_nearby_waiting(app, slug)
        
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Not found', 'message': '취소할 수 있는 대기 정보를 찾을 수 없습니다.'}), 404

@app.route('/api/<slug>/customer', methods=['POST'])
def api_get_or_create_customer(slug):
    data = request.json
    phone = data.get('phone')
    if not phone: return jsonify({'error': 'No phone'}), 400
    
    cust = Customer.query.filter_by(store_id=slug, phone=phone).first()
    if not cust:
        cust = Customer(store_id=slug, phone=phone, points=0)
        db.session.add(cust)
        db.session.commit()
    else:
        # Check Expiration (Final accumulation + 1 year)
        if cust.last_accumulation_at and cust.last_accumulation_at < datetime.utcnow() - timedelta(days=365):
            cust.points = 0
            db.session.commit()
            
    return jsonify(cust.to_dict())

@socketio.on('join')
def on_join(data):
    sid = data.get('store_id')
    if sid:
        from flask_socketio import join_room
        join_room(sid)

@socketio.on('place_order')
def on_place_order(data):
    try:
        slug = data.get('store_id')
        items = data.get('items')
        table_id = data.get('table_id')
        session_id = data.get('session_id')
        total_price = data.get('total_price')
        phone = data.get('phone')

        if not items:
            print("⚠️ [주문 오류] 빈 주문 목록이 전송되었습니다.")
            return

        order_id = str(random.randint(100, 999))
        new_order = Order(id=order_id, store_id=slug, table_id=table_id, session_id=session_id, total_price=total_price, phone=phone)
        db.session.add(new_order)
        
        for item in items:
            # menu_id가 누락되었을 경우 0으로 대체 (AI 초기 메뉴 등)
            m_id = item.get('id', 0)
            oi = OrderItem(order_id=order_id, menu_id=m_id, name=item['name'], price=item['price'], quantity=item['quantity'])
            db.session.add(oi)
        
        db.session.commit()
        print(f"✅ [주문 성공] {slug} 테이블 {table_id} - 주문번호 {order_id}")
        socketio.emit('new_order', new_order.to_dict(), room=slug)
    except Exception as e:
        db.session.rollback()
        print(f"❌ [주문 처리 오류] {e}")
        socketio.emit('order_error', {'message': '주문 처리 중 서버 오류가 발생했습니다.'})

@socketio.on('set_ready')
def on_set_ready(data):
    try:
        oid = data.get('order_id')
        if not oid: return
        order = db.session.get(Order, oid)
        if order:
            order.status = 'ready'
            db.session.commit()
            # 매장 내 모든 관련 대시보드와 손님에게 상태 변경 알림
            socketio.emit('order_status_update', order.to_dict(), room=order.store_id)
            print(f"✅ [주방] 주문 {oid} 조리 완료 처리됨")
    except Exception as e:
        db.session.rollback()
        print(f"❌ [주방 오류] 조리 완료 처리 중 에러: {e}")

@socketio.on('set_served')
def on_set_served(data):
    sid = data.get('session_id')
    slug = data.get('store_id')
    orders = Order.query.filter_by(store_id=slug, session_id=sid, status='ready').all()
    if not orders:
        # [수정] 주문이 없을 경우 조기 종료 (tid=None으로 emit하던 버그 방지)
        print(f"⚠️ [set_served] 처리할 주문 없음 (session_id={sid})")
        return
    tid = orders[0].table_id
    for o in orders:
        o.status = 'served'
    db.session.commit()
    socketio.emit('table_status_update', {'store_id': slug, 'session_id': sid, 'table_id': tid, 'status': 'served'}, room=slug)

@socketio.on('set_paid')
def on_set_paid(data):
    slug = data.get('store_id')
    sid = data.get('session_id')
    phone = data.get('phone')
    use_points = data.get('use_points', 0)
    
    orders = Order.query.filter_by(store_id=slug, session_id=sid, status='served').all()
    if not orders: return
    
    # 테이블 번호 추출
    tid = orders[0].table_id
    total_sum = sum(o.total_price for o in orders)
    
    if phone:
        cust = Customer.query.filter_by(store_id=slug, phone=phone).first()
        if cust:
            # Check Expiration (Final accumulation + 1 year)
            if cust.last_accumulation_at and cust.last_accumulation_at < datetime.utcnow() - timedelta(days=365):
                cust.points = 0
            
            # Point Usage (Check >= 10,000 condition in UI, but enforce here)
            if use_points > 0 and cust.points >= 10000:
                actual_use = min(cust.points, use_points)
                cust.points -= actual_use
                db.session.add(PointTransaction(customer_id=cust.id, store_id=slug, amount=-actual_use, description="포인트 사용 포인트 감면"))
            
            # [수정] 포인트 적립륙 동적화: store.point_ratio 설정값 사용 (1% 하드코딩에서 변경)
            store_for_ratio = db.session.get(Store, slug)
            ratio = (store_for_ratio.point_ratio if store_for_ratio and store_for_ratio.point_ratio and store_for_ratio.point_ratio > 0 else 0.01)
            acc_amount = int(total_sum * ratio)
            cust.points += acc_amount
            cust.visit_count += 1
            cust.total_spent += total_sum
            cust.last_accumulation_at = datetime.utcnow()
            db.session.add(PointTransaction(customer_id=cust.id, store_id=slug, amount=acc_amount, description="식비 적립"))
    
    for o in orders:
        o.status = 'paid'
        o.paid_at = datetime.utcnow()
    
    db.session.commit()
    socketio.emit('table_status_update', {'store_id': slug, 'session_id': sid, 'table_id': tid, 'status': 'paid'}, room=slug)

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

if __name__ == '__main__':
    # [1단계] Render는 PORT 환경변수를 통해 동적으로 포트를 할당합니다.
    port = int(os.environ.get('PORT', 10000))
    print(f"🔥 [서버 구동] 포트 {port}번에서 MQnet Central을 기동합니다...")
    
    # [2단계] 데이터베이스 점검 로직
    with app.app_context():
        try:
            print(f"🔍 [DB 점검] 현재 {db_url.split('@')[-1] if '@' in db_url else 'SQLite'} 데이터베이스를 사용 중입니다.")
            db.create_all()
            print("✅ [DB 준비 완료] 시스템이 가동됩니다.")
        except Exception as e:
            print(f"⚠️ [DB 경고] 데이터베이스 점검 중 오류 발생: {e}")

    # [3단계] 서버 실행
    is_render = 'RENDER' in os.environ
    debug_mode = not is_render  # Render가 아닐 때만 디버그 모드 활성
    
    print(f"🚀 [최종 시스템 가동] 접속 가능 (포트: {port}, 디버그: {debug_mode})")
    socketio.run(app, debug=debug_mode, host='0.0.0.0', port=port)
