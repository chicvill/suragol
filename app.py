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
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, desc, text
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

if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    print(f"🌐 [클라우드 DB 모드] Supabase 데이터베이스에 연결합니다.")
else:
    # 🏠 내 컴퓨터(로컬)에서는 이 가벼운 파일 DB를 사용합니다 (에러 방지)
    db_url = 'sqlite:///local_test.db'
    print("🏠 [로컬 모드] 'local_test.db' 파일을 사용하여 테스트를 준비합니다.")

# ---------------------------------------------------------
# DB 연결 설정
# ---------------------------------------------------------
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
            ("position", "VARCHAR(50)")
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

        # 2. Stores 테이블 컬럼 보강
        try:
            db.session.execute(text("ALTER TABLE stores ADD COLUMN monthly_fee INTEGER DEFAULT 50000"))
            db.session.execute(text("ALTER TABLE stores ADD COLUMN attendance_pin VARCHAR(4) DEFAULT '1234'"))
            db.session.execute(text("ALTER TABLE stores ADD COLUMN recommended_by INTEGER REFERENCES users(id)"))
            db.session.commit()
            print("✅ [성공] stores 테이블에 monthly_fee, attendance_pin, recommended_by 컬럼이 추가되었습니다.")
        except Exception as e:
            db.session.rollback()
            print(f"ℹ️ [알림] stores 컬럼 체크 완료 ({'이미 존재함' if 'already exists' in str(e).lower() else e})")
            print(f"ℹ️ [알림] stores.monthly_fee 체크 완료 ({'이미 존재함' if 'already exists' in str(e).lower() else e})")

        print("🚀 [완료] 모든 데이터베이스 구조가 최신 상태로 동기화되었습니다.")
    except Exception as e:
        print(f"❌ [치명적 오류] DB 초기화 실패: {e}")
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
        # 직원은 본인이 담당한 매장 목록
        stores = Store.query.filter_by(recommended_by=user_id).all()
        
    return render_template('index.html', 
                         logged_in=True, 
                         user=user, 
                         role=role, 
                         store=store, 
                         stores=stores)

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
        # 역할 선택 (admin은 자가 가입 불가 - staff로 강제 처리)
        selected_role = request.form.get('role', 'staff')
        if selected_role not in ['owner', 'manager', 'worker', 'staff']:
            selected_role = 'staff'

        # 약관 동의 체크
        agree_profit = 'agree_profit' in request.form
        agree_privacy = 'agree_privacy' in request.form
        agree_age = 'agree_age' in request.form
        agree_not_robot = 'agree_not_robot' in request.form
        agree_termination = 'agree_termination' in request.form

        if not all([agree_profit, agree_privacy, agree_age, agree_not_robot, agree_termination]):
            flash("모든 필수 약관에 동의하셔야 가입 신청이 가능합니다.")
            return redirect(url_for('signup'))

        if password != confirm_password:
            flash("비밀번호가 일치하지 않습니다.")
            return redirect(url_for('signup'))

        if User.query.filter_by(username=username).first():
            flash("이미 사용 중인 아이디입니다.")
            return redirect(url_for('signup'))

        role_labels = {'owner': '점주', 'manager': '점장', 'worker': '현장 근로자', 'staff': '파트너'}
        new_user = User(
            username=username,
            password=generate_password_hash(password),
            role=selected_role,
            full_name=full_name,
            phone=phone,
            is_approved=False,  # 모든 자가 가입은 관리자 승인 필요
            agreed_at=datetime.utcnow()
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
    """역할별 맞춤형 대시보드 동적 서빙"""
    role = session.get('role', 'worker')
    print(f"\n📢 [DASHBOARD ACCESS] User: {session.get('username')}, Role: {role}")
    
    now = datetime.now()
    start_date = now.strftime('%Y-%m-%d')
    end_date = now.strftime('%Y-%m-%d')
    user_id = session.get('user_id')
    store_id = session.get('store_id')
    
    # 1. 통계 데이터 초기화
    stores = []
    total_revenue = 0
    total_orders = 0
    total_waiting = 0
    my_commission = 0
    
    # 2. 역할별 데이터 필터링
    if role == 'admin':
        stores = Store.query.all()
        total_revenue = db.session.query(func.sum(Order.total_price)).filter(Order.status == 'paid').scalar() or 0
        total_orders = Order.query.count()
        total_waiting = Waiting.query.count()
        return render_template('admin/dashboard_admin.html', stores=stores, total_revenue=total_revenue, total_orders=total_orders, total_waiting=total_waiting, now=now)
    elif role == 'staff':
        stores = Store.query.filter_by(recommended_by=user_id).all()
        store_ids = [s.id for s in stores]
        if store_ids:
            total_revenue = db.session.query(func.sum(Order.total_price)).filter(Order.store_id.in_(store_ids), Order.status == 'paid').scalar() or 0
            total_orders = Order.query.filter(Order.store_id.in_(store_ids)).count()
            total_waiting = Waiting.query.filter(Waiting.store_id.in_(store_ids)).count()
        
        # 수당 계산 (MQutils 활용)
        now = datetime.now()
        for s in stores:
            my_commission += calculate_commission(s, now)
        return render_template('admin/dashboard_staff.html', stores=stores, total_revenue=total_revenue, my_commission=my_commission, now=now)
    elif store_id:
        # 가맹점주(Owner) 및 점장(Manager)
        stores = Store.query.filter_by(id=store_id).all()
        total_revenue = db.session.query(func.sum(Order.total_price)).filter(Order.store_id == store_id, Order.status == 'paid').scalar() or 0
        selected_store = stores[0] if stores else None
        # 리스트 반환
        worker_reports = []
        partner_reports = []
        
        if selected_store:
            # 해당 매장 소속 Worker 명단 추출
            workers = User.query.filter_by(store_id=selected_store.id, role='worker').all()
            for w in workers:
                worker_reports.append({
                    'user': w,
                    'hours': 0, # 근태 데이터 미연동 시 0처리
                    'expected_wage': 0
                })
                
            if selected_store.recommended_by:
                partner = User.query.get(selected_store.recommended_by)
                if partner:
                    partner_reports.append({
                        'user': partner,
                        'period_sales': 0, 
                        'commission': 0
                    })
        
        print(f"📊 [STAFF MGMT] Found {len(worker_reports)} workers for Store: {selected_store.id if selected_store else 'NONE'}")

        return render_template('admin/staff_mgmt.html', 
                               selected_store=selected_store,
                               selected_slug=selected_store.id if selected_store else None,
                               store=selected_store,
                               worker_reports=worker_reports,
                               partner_reports=partner_reports,
                               stores=Store.query.all() if role == 'admin' else [],
                               start_date=start_date,
                               end_date=end_date,
                               now=now)
    
    return redirect(url_for('index'))

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
        # 직원은 본인이 담당한 매장만 리스팅
        stores = Store.query.filter_by(recommended_by=user_id).order_by(Store.created_at.desc()).all()
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
@staff_required
def admin_store_config(slug):
    store = db.session.get(Store, slug)
    user_id = session.get('user_id')
    role = session.get('role')

    # 보안 체크: 일반 직원이 본인 담당이 아닌 매장에 접근할 경우 차단
    if role == 'staff' and store.recommended_by != user_id:
        flash("해당 업소에 대한 관리 권한이 없습니다.")
        return redirect(url_for('admin_stores'))
    
    if request.method == 'POST':
        # Now we allow STAFF to update menus, but NOT the manager assignment
        store.name = request.form.get('name')
        store.business_no = request.form.get('business_no')
        store.ceo_name = request.form.get('ceo_name')
        store.business_email = request.form.get('business_email')
        
        # Responsible Staff (recommended_by) is ONLY changeable by Admin
        # Monthly Fee is changeable by Admin or Staff (Sales Partner)
        if session.get('role') == 'admin':
            store.recommended_by = request.form.get('recommended_by')
        
        if session.get('role') in ['admin', 'staff']:
            store.monthly_fee = int(request.form.get('monthly_fee', 50000))
        
        store.menu_data = json.loads(request.form.get('menu_data', '{}'))
        db.session.commit()
        flash(f"{store.name}의 설정이 저장되었습니다.")
        return redirect(url_for('admin_stores'))
    # 담당 직원 선택 목록에 관리자(admin) 및 사장님(owner)도 포함하도록 수정
    staffs = User.query.filter(User.role.in_(['staff', 'admin', 'owner'])).all()
    return render_template('admin/store_config.html', store=store, staffs=staffs)

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
@admin_required
def admin_user_approve(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.is_approved = True
        db.session.commit()
        flash(f"{user.username} 님의 가입 신청이 최종 승인되었습니다.")
    return redirect(url_for('admin_users'))

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
    
    # 역할, 소속 매장, 실명, 연락처, 시급
    user.role = data.get('role', user.role)
    store_id = data.get('store_id', '').strip()
    user.store_id = store_id if store_id else None
    user.full_name = data.get('full_name', user.full_name)
    user.phone = data.get('phone', user.phone)
    user.hourly_rate = int(data.get('hourly_rate', user.hourly_rate or 10000))
    
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/admin/billing')
@admin_required
def admin_billing():
    stores = Store.query.all()
    unpaid = Store.query.filter_by(payment_status='unpaid').count()
    sus = Store.query.filter_by(status='suspended').count()
    return render_template('admin/billing.html', stores=stores, unpaid_count=unpaid, suspended_count=sus, total_stores=len(stores))

# ---------------------------------------------------------
# 제휴 파트너 정산 보조 기능 (매월 25일 정산용 인쇄 페이지)
# ---------------------------------------------------------

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

@app.route('/api/admin/upload', methods=['POST'])
@staff_required
def api_upload_image():
    file = request.files.get('file')
    if not file: return jsonify({'error': 'No file'}), 400
    filename = str(uuid.uuid4())[:12] + "_" + file.filename
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
    store = db.session.get(Store, slug)
    if 'uid' not in session: session['uid'] = str(random.randint(100, 999))
    return render_template('customer.html', store=store, table_id=table_id, session_id=session['uid'])

@app.route('/<slug>/counter')
@store_access_required
def counter_view(slug):
    store = db.session.get(Store, slug)
    if not store: return redirect(url_for('index'))
    return render_template('counter.html', store=store)

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
    now = datetime.now()
    
    if period == 'week':
        # 이번 주 월요일 00:00부터
        start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'month':
        # 이번 달 1일 00:00부터
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == 'year':
        # 올해 1월 1일 00:00부터
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        # 오늘 00:00부터
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
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

@app.route('/api/<slug>/stats/reset', methods=['POST'])
@store_access_required
def api_reset_stats(slug):
    # 실제로는 데이터를 삭제하지 않고 통계 기준점을 업데이트하는 방식이 권장되지만,
    # 여기서는 간단하게 오늘 결제된 건들의 paid_at을 어제로 변경하여 초기화 효과를 냅니다.
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today_start - timedelta(seconds=1)
    
    Order.query.filter(Order.store_id == slug, Order.status == 'paid', Order.paid_at >= today_start)\
        .update({Order.paid_at: yesterday}, synchronize_session=False)
    
    db.session.commit()
    return jsonify({'status': 'success'})

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
    
    # Notify staff via SocketIO
    socketio.emit('new_service_request', new_req.to_dict(), room=slug)
    return jsonify({'status': 'success', 'request': new_req.to_dict()})

@app.route('/api/<slug>/service_requests')
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
    user = db.session.get(User, user_id)  # 🔧 버그 수정: user 변수 조회 추가
    
    # [권한 체크] 현장 근로자(worker) 및 점장(manager)만 출퇴근 가능
    if role not in ['worker', 'manager']:
        return jsonify({'status': 'error', 'message': '현장 근로자 및 점장 계정 전용 기능입니다.'}), 403
    
    # [소속 체크] 매장에 소속되지 않은 유저가 QR을 찍은 경우 차단
    if not user or not user.store_id or user.store_id != slug:
        return jsonify({'status': 'error', 'message': '해당 매장에 등록되지 않은 근로자입니다. 매장 배정 후 이용해 주세요.'}), 403

    # 이미 출근 중이거나 승인 대기 중인지 확인
    existing = Attendance.query.filter(Attendance.user_id==user_id, Attendance.store_id==slug, Attendance.status.in_(['working', 'pending_in'])).first()
    if existing:
        return jsonify({'status': 'error', 'message': '현재 업무 대기 또는 진행 중입니다.'}), 400
    
    new_att = Attendance(user_id=user_id, store_id=slug, status='pending_in')
    db.session.add(new_att)
    db.session.commit()
    
    # 관리자에게 출근 승인 요청 알림
    socketio.emit('attendance_request', {'id': new_att.id, 'name': session.get('username'), 'type': '출근'}, room=slug)
    return jsonify({'status': 'success', 'message': '관리자 승인 대기 중...'})

@app.route('/api/<slug>/attendance/check-out', methods=['POST'])
@login_required
def api_staff_check_out(slug):
    user_id = session.get('user_id')
    role = session.get('role')
    if role not in ['worker', 'manager']:
        return jsonify({'status': 'error', 'message': '현장 근로자 및 점장 계정 전용 기능입니다.'}), 403

    att = Attendance.query.filter_by(user_id=user_id, store_id=slug, status='working').first()
    if not att:
        return jsonify({'status': 'error', 'message': '업무 중인 상태가 아닙니다.'}), 400
    
    att.status = 'pending_out'
    db.session.commit()
    
    # 관리자에게 퇴근 승인 요청 알림
    socketio.emit('attendance_request', {'id': att.id, 'name': session.get('username'), 'type': '퇴근'}, room=slug)
    return jsonify({'status': 'success', 'message': '퇴근 승인 대기 중...'})

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
    if not store or store.attendance_pin != pin:
        return jsonify({'status': 'error', 'message': '보안 코드가 일치하지 않습니다.'}), 400
    
    # 사장님이 선택한 ID들만 필터링하여 승인
    pending_list = Attendance.query.filter(Attendance.id.in_(selected_ids)).all()
    
    count = 0
    now = datetime.utcnow()
    for att in pending_list:
        if att.status == 'pending_in':
            att.check_in_at = now
            att.status = 'working'
            count += 1
        elif att.status == 'pending_out':
            att.check_out_at = now
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
    if not store or store.attendance_pin != pin:
        return jsonify({'status': 'error', 'message': '보안 코드가 일치하지 않습니다.'}), 400
        
    att = db.session.get(Attendance, att_id)
    if not att: return jsonify({'error': 'Not found'}), 404
    
    if att.status == 'pending_in':
        att.check_in_at = datetime.utcnow()
        att.status = 'working'
    elif att.status == 'pending_out':
        att.check_out_at = datetime.utcnow()
        # 근무 시간(분) 계산
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
    
    # 현재 비밀번호 확인 절차 (보안 강화)
    if store.attendance_pin != old_pin:
        return jsonify({'status': 'error', 'message': '현재 보안 코드가 일치하지 않아 변경할 수 없습니다.'}), 400
        
    if not new_pin or len(new_pin) != 4:
        return jsonify({'status': 'error', 'message': '새 보안 코드는 4자리 숫자여야 합니다.'}), 400
        
    store.attendance_pin = new_pin
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
        user.role = data.get('role', user.role) # 역할 변경 기능 추가
        user.phone = data.get('phone', user.phone) # 연락처 변경 기능 추가
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/<slug>/customers')
@store_access_required
def api_get_store_customers(slug):
    """현재 매장의 모든 고객 리스트와 포인트 현황을 반환합니다."""
    customers = Customer.query.filter_by(store_id=slug).order_by(Customer.visit_count.desc()).all()
    return jsonify([c.to_dict() for c in customers])

# ---------------------------------------------------------
# 웨이팅(예약) 시스템 API
# ---------------------------------------------------------

@app.route('/api/<slug>/waiting', methods=['POST'])
def api_create_waiting(slug):
    data = request.json
    phone = data.get('phone', '010-0000-0000')
    people = int(data.get('people', 1))
    
    # 오늘 접수된 대기 팀 수 계산 (대기 번호 부여용)
    now_local = datetime.now()
    count = Waiting.query.filter_by(store_id=slug).filter(Waiting.created_at >= datetime(now_local.year, now_local.month, now_local.day)).count()
    
    new_wait = Waiting(store_id=slug, phone=phone, people=people, waiting_no=count+1)
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
    slug = data.get('store_id')
    items = data.get('items')
    table_id = data.get('table_id')
    session_id = data.get('session_id')
    total_price = data.get('total_price')
    phone = data.get('phone') # Point accumulation phone

    order_id = str(uuid.uuid4())[:8]
    new_order = Order(id=order_id, store_id=slug, table_id=table_id, session_id=session_id, total_price=total_price, phone=phone)
    db.session.add(new_order)
    
    for item in items:
        oi = OrderItem(order_id=order_id, menu_id=item['id'], name=item['name'], price=item['price'], quantity=item['quantity'])
        db.session.add(oi)
    
    db.session.commit()
    socketio.emit('new_order', new_order.to_dict(), room=slug)

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
    # 첫 번째 주문에서 table_id 추출 (현황판 삭제용)
    tid = orders[0].table_id if orders else None
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
            
            # Point Accumulation (1% of total)
            acc_amount = int(total_sum * 0.01)
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

# [백업 스케줄러] 매주 월요일 자정 0시 실행
if not scheduler.get_job('weekly_backup_job'):
    models_to_backup = [
        ('운영자 및 유저', User), ('가맹점 정보', Store), ('주문 내역', Order),
        ('포인트 트랜잭션', PointTransaction), ('고객 명단', Customer)
    ]
    scheduler.add_job(id='weekly_backup_job', func=send_daily_backup, args=(app, db, models_to_backup), trigger='cron', day_of_week='mon', hour=0, minute=0)
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
    print(f"🚀 [최종 시스템 가동] 이제 접속이 가능합니다 (포트 {port})")
    socketio.run(app, debug=True, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
