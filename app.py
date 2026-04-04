# -*- coding: utf-8 -*-
import os
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
import threading

# 환경변수 로드
load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------
# Flask 앱 초기화 및 설정
# ---------------------------------------------------------
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1) # HTTPS 프록시 헤더 처리
app.config['SECRET_KEY'] = 'suragol-secret-key-2026'
app.url_map.strict_slashes = False # URL 끝 슬래시(/) 유무에 상관없이 접속 허용
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'images')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# DB 연결
db_url = os.environ.get('DATABASE_URL', 'sqlite:///suragol.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from models import db, Order, OrderItem, Waiting, Store, User, SystemConfig, TaxInvoice, ServiceRequest, Customer, PointTransaction
db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# MQutils Integration (Solapi SMS)
try:
    from MQutils import SolapiMessenger
except ImportError:
    class SolapiMessenger:
        def __init__(self, *args, **kwargs): pass
        def send_sms(self, to, msg): print(f"[SIM] Missing MQutils. SMS to {to}: {msg}")

# 템플릿 전역 변수 설정
@app.context_processor
def inject_globals():
    return {'timedelta': timedelta, 'now': datetime.utcnow()}

# ---------------------------------------------------------
# 공통 유틸리티 및 권한 제어 (MQutils 모듈에서 활용)
# ---------------------------------------------------------
from MQutils import (
    login_required, admin_required, staff_required, store_access_required,
    send_waiting_sms, check_nearby_waiting
)

# ---------------------------------------------------------
# 매장별 서비스 라우트
# ---------------------------------------------------------

@app.route('/')
@login_required
def store_selection():
    user_id = session.get('user_id')
    user_role = session.get('role')
    user_store_id = session.get('store_id')
    
    if user_role == 'admin':
        # 최고 관리자는 모든 매장을 볼 수 있음
        stores = Store.query.all()
    elif user_role == 'staff':
        # 직원은 본인이 담당자로 지정된 매장만 조회 가능
        stores = Store.query.filter_by(recommended_by=user_id).all()
    else:
        # 매장 점주는 본인 매장만 조회 가능
        stores = Store.query.filter_by(id=user_store_id).all() if user_store_id else []
        
        # 만약 담당 매장이 1개뿐이라면 즉시 해당 매장으로 리다이렉트 (UX 향상)
        if len(stores) == 1:
            return redirect(url_for('index', slug=stores[0].id))
            
    return render_template('store_selection.html', stores=stores)

@app.route('/<slug>')
def index(slug):
    # 이모지는 윈도우 환경에서 인코딩 에러를 유발할 수 있어 제거했습니다.
    print(f"--- [Domain Request] Accessing Slug: {slug} ---")
    store = db.session.get(Store, slug)
    if not store:
        print(f"--- [Error] Store '{slug}' not found in DB. Redirecting to portal. ---")
        return redirect(url_for('store_selection'))
    
    try: 
        return render_template('index.html', store=store)
    except Exception as e:
        print(f"--- [Template Error] Falling back to customer view: {e} ---")
        return redirect(url_for('customer_view', slug=slug, table_id=1))

@app.route('/<slug>/customer/<int:table_id>')
def customer_view(slug, table_id):
    store = db.session.get(Store, slug)
    if 'uid' not in session: session['uid'] = str(random.randint(100, 999))
    return render_template('customer.html', store=store, table_id=table_id, session_id=session['uid'])

@app.route('/<slug>/kitchen')
@store_access_required
def kitchen_view(slug):
    store = db.session.get(Store, slug)
    return render_template('kitchen.html', store=store)

@app.route('/<slug>/counter')
@store_access_required
def counter_view(slug):
    store = db.session.get(Store, slug)
    return render_template('counter.html', store=store)

@app.route('/<slug>/qr-print')
@store_access_required
def qr_print_view(slug):
    store = db.session.get(Store, slug)
    if not store: return redirect(url_for('store_selection'))
    return render_template('qr_print.html', store=store)

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
    # 기본적으로 오늘(UTC 기준)의 데이터를 가져옵니다.
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 1. 오늘 총 매출
    total_sales = db.session.query(func.sum(Order.total_price))\
        .filter(Order.store_id == slug, Order.status == 'paid', Order.paid_at >= today_start)\
        .scalar() or 0
        
    # 2. 인기 메뉴 TOP 5
    best_items = db.session.query(OrderItem.name, func.sum(OrderItem.quantity).label('total_count'))\
        .join(Order, Order.id == OrderItem.order_id)\
        .filter(Order.store_id == slug, Order.status == 'paid', Order.paid_at >= today_start)\
        .group_by(OrderItem.name)\
        .order_by(desc('total_count'))\
        .limit(5).all()
    
    best_menu = [{'name': name, 'count': int(count)} for name, count in best_items]
    
    return jsonify({
        'daily_sales': int(total_sales),
        'best_menu': best_menu,
        'date': today_start.strftime('%Y-%m-%d')
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

# ---------------------------------------------------------
# 통합 관리자 센터 (MQnet Central)
# ---------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session.update({'user_id':user.id, 'username':user.username, 'role':user.role, 'store_id':user.store_id})
            if user.role in ['admin', 'staff']: return redirect(url_for('admin_dashboard'))
            return redirect(url_for('counter_view', slug=user.store_id))
        flash("로그인 정보를 확인해 주세요.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin/')
@app.route('/admin')
@staff_required
def admin_dashboard():
    stores = Store.query.all()
    total_revenue = db.session.query(func.sum(Order.total_price)).filter(Order.status == 'paid').scalar() or 0 if session.get('role') == 'admin' else 0
    total_orders = Order.query.count()
    total_waiting = Waiting.query.count()
    
    # Calculate Commission for the current staff member (if applicable)
    user_id = session.get('user_id')
    my_commission = 0
    if session.get('role') == 'staff':
        my_stores = Store.query.filter_by(recommended_by=user_id, payment_status='paid').all()
        now = datetime.utcnow()
        for s in my_stores:
            delta = now - s.created_at
            # Rule: -1 month for free, -1 month for first paid month = -2 months
            paid_months = max(0, (delta.days // 30) - 2)
            my_commission += (paid_months * 50000 * 0.1)
            
    return render_template('admin/dashboard.html', stores=stores, total_revenue=total_revenue, total_orders=total_orders, total_waiting=total_waiting, my_commission=int(my_commission))

@app.route('/admin/manual/staff')
@staff_required
def staff_manual_page():
    try:
        with open('manuals/staff_manual.md', 'r', encoding='utf-8') as f:
            content = f.read()
        return render_template('admin/staff_manual_view.html', content=content)
    except: return "매뉴얼 파일을 찾을 수 없습니다.", 404

@app.route('/admin/stores')
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
        
        # Responsible Staff (recommended_by) and Monthly Fee is ONLY changeable by Admin
        if session.get('role') == 'admin':
            store.recommended_by = request.form.get('recommended_by')
            store.monthly_fee = int(request.form.get('monthly_fee', 50000))
        
        store.menu_data = json.loads(request.form.get('menu_data', '{}'))
        db.session.commit()
        flash(f"{store.name}의 설정이 저장되었습니다.")
        return redirect(url_for('admin_stores'))
    staffs = User.query.filter_by(role='staff').all()
    return render_template('admin/store_config.html', store=store, staffs=staffs)

@app.route('/admin/performance')
@staff_required
def admin_performance():
    user_id = session.get('user_id')
    role = session.get('role')
    performance_data = []
    staffs = User.query.filter_by(role='staff').all() if role == 'admin' else User.query.filter_by(id=user_id).all()
    
    for staff in staffs:
        stores = Store.query.filter_by(recommended_by=staff.id).all()
        total_rev = 0
        now = datetime.utcnow()
        for s in stores:
            if s.payment_status == 'paid':
                # First month is free, so subtract 1 from total months
                delta = now - s.created_at
                total_months = delta.days // 30
                paid_months = max(0, total_months - 1) 
                
                # If it's the 2nd month (total_months=1) and they paid 50k, 
                # but the user said "매출은 0으로 산출됨" for that first 50k after free month.
                # So it means we only start counting revenue from total_months >= 2?
                # "첫달은 무료로 사용하고 다음달 26일 5만원이 입금되었을때 매출은 0으로 산출됨"
                # This implies:
                # Month 0: Free (Revenue 0)
                # Month 1: 50k paid (Revenue still 0 for staff?)
                # Month 2: 50k paid (Revenue starts here?)
                # Let's subtract 2 months to be safe based on "매출은 0으로 산출됨" for the first paid month.
                commissionable_months = max(0, total_months - 2) 
                total_rev += (commissionable_months * (s.monthly_fee or 50000))
        
        performance_data.append({
            'staff_name': staff.username, 'id': staff.id, 'store_count': len(stores),
            'paid_count': len([s for s in stores if s.payment_status == 'paid']),
            'revenue': total_rev, 
            'commission': int(total_rev * 0.1), # 10% Commission
            'stores': stores
        })
    return render_template('admin/performance.html', data=performance_data, role=role)

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
            new_user = User(username=username, password=generate_password_hash(password), role=role, store_id=sid if sid != 'null' else None)
            db.session.add(new_user)
            db.session.commit()
            flash(f"{username} 계정이 생성 및 승격되었습니다.")
        return redirect(url_for('admin_users'))
    users = User.query.all()
    stores = Store.query.all()
    return render_template('admin/users.html', users=users, stores=stores)

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

@app.route('/admin/billing')
@admin_required
def admin_billing():
    stores = Store.query.all()
    unpaid = Store.query.filter_by(payment_status='unpaid').count()
    sus = Store.query.filter_by(status='suspended').count()
    return render_template('admin/billing.html', stores=stores, unpaid_count=unpaid, suspended_count=sus, total_stores=len(stores))

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
@store_access_required
def api_get_service_requests(slug):
    reqs = ServiceRequest.query.filter_by(store_id=slug, status='pending').order_by(ServiceRequest.created_at.desc()).all()
    return jsonify([r.to_dict() for r in reqs])

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
    oid = data.get('order_id')
    order = db.session.get(Order, oid)
    if order:
        order.status = 'ready'
        db.session.commit()
        socketio.emit('order_status_update', order.to_dict(), room=order.store_id)

@socketio.on('set_served')
def on_set_served(data):
    sid = data.get('session_id')
    slug = data.get('store_id')
    orders = Order.query.filter_by(store_id=slug, session_id=sid, status='ready').all()
    for o in orders:
        o.status = 'served'
    db.session.commit()
    socketio.emit('table_status_update', {'store_id': slug, 'session_id': sid, 'status': 'served'}, room=slug)

@socketio.on('set_paid')
def on_set_paid(data):
    slug = data.get('store_id')
    sid = data.get('session_id')
    phone = data.get('phone')
    use_points = data.get('use_points', 0)
    
    orders = Order.query.filter_by(store_id=slug, session_id=sid, status='served').all()
    if not orders: return
    
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
    socketio.emit('table_status_update', {'store_id': slug, 'session_id': sid, 'status': 'paid'}, room=slug)

if __name__ == '__main__':
    with app.app_context(): 
        db.create_all()
        # Migration for existing DB
        try:
            db.session.execute(text("ALTER TABLE orders ADD COLUMN phone VARCHAR(20)"))
            db.session.commit()
            print("🚀 Migrated: Added 'phone' to 'orders'")
        except: db.session.rollback()

        try:
            db.session.execute(text("ALTER TABLE stores ADD COLUMN monthly_fee INTEGER DEFAULT 50000"))
            db.session.commit()
            print("🚀 Migrated: Added 'monthly_fee' to 'stores'")
        except: db.session.rollback()

        try:
            db.session.execute(text("ALTER TABLE waiting ADD COLUMN nearby_notified BOOLEAN DEFAULT FALSE"))
            db.session.execute(text("ALTER TABLE waiting ADD COLUMN enter_notified BOOLEAN DEFAULT FALSE"))
            db.session.commit()
            print("🚀 Migrated: Added columns to 'waiting'")
        except: db.session.rollback()

        try:
            db.session.execute(text("ALTER TABLE customers ADD COLUMN visit_count INTEGER DEFAULT 0"))
            db.session.execute(text("ALTER TABLE customers ADD COLUMN total_spent INTEGER DEFAULT 0"))
            db.session.commit()
            print("🚀 Migrated: Added columns to 'customers'")
        except: db.session.rollback()

    # Render의 기본 포트(10000)를 무시하고 호스트인 Cloudflare 터널과 약속된 8888 포트로 고정합니다.
    socketio.run(app, debug=False, host='0.0.0.0', port=8888, allow_unsafe_werkzeug=True)
