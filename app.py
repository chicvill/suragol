import os
import sys
import json
import time
import socket
import random
import uuid
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_socketio import SocketIO, emit
from sqlalchemy import func, desc, text
from werkzeug.middleware.proxy_fix import ProxyFix
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
    # 로컬 폴더(C:\Users\USER\Dev\왕궁중화요리\MQutils)에서 임포트 시도
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

from models import db, Order, OrderItem, Waiting

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SECRET_KEY'] = 'suragol-secret!'
# Supabase PostgreSQL 및 기본 SQLite 지원
db_url = os.environ.get('DATABASE_URL', 'sqlite:///suragol.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 프록시 설정 (Cloudflare Tunnel의 HTTPS 연결을 올바르게 인식하도록 함)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

# 메신저 서비스 초기화
# .env에 등록된 정보를 사용하거나 수동으로 키를 입력할 수 있습니다.
messenger = SolapiMessenger()

# DB 초기화 및 이미지 자동 복사 (마이그레이션 용도)
try:
    import glob, shutil
    artifact_dir = r"C:\Users\USER\.gemini\antigravity\brain\a12b6296-2531-461a-80a0-70328ad88362"
    static_img_dir = os.path.join(BASE_DIR, "static", "images")
    os.makedirs(static_img_dir, exist_ok=True)
    for t in ['pork', 'beef', 'noodle', 'stew', 'meal', 'egg', 'soju', 'beer', 'makgeolli', 'cola', 'cider']:
        files = glob.glob(os.path.join(artifact_dir, f"{t}_*.png"))
        if files:
            latest_file = max(files, key=os.path.getctime)
            dest = os.path.join(static_img_dir, f"{t}.png")
            shutil.copy(latest_file, dest)
            print(f"[자동복사] {t}.png 이미지 업데이트 완료!")
except Exception as img_e:
    print(f"[자동복사 오류] {img_e}")

db.init_app(app)
with app.app_context():
    db.create_all()
    try:
        db.session.execute(text("ALTER TABLE orders ADD COLUMN session_id TEXT"))
        db.session.commit()
    except:
        db.session.rollback()
    
    # Waiting 테이블 migration: updated_at 컬럼 추가
    try:
        db.session.execute(text("ALTER TABLE waiting ADD COLUMN updated_at DATETIME"))
        db.session.commit()
        print("[Info] Added updated_at column to waiting table.")
    except:
        db.session.rollback()

    # Waiting 테이블 migration: waiting_no 필드 추가
    try:
        db.session.execute(text("ALTER TABLE waiting ADD COLUMN waiting_no INTEGER"))
        db.session.commit()
        print("[Info] Added waiting_no column to waiting table.")
    except Exception as e:
        db.session.rollback()

# SocketIO 설정
socketio = SocketIO(app, cors_allowed_origins="*")

# 메뉴 데이터 (수라골 - 한식 고기구이)
# 메뉴 데이터 (수라골 - 한식 고기구이)
menu = {
    "구이류": [
        {"id": 1, "name": "수제 돼지양념구이", "price": 19000, "image": "/static/images/pork.png"},
        {"id": 2, "name": "프리미엄 생삼겹살", "price": 18000, "image": "/static/images/pork.png"},
        {"id": 3, "name": "한우 특수부위 모듬", "price": 55000, "image": "/static/images/beef.png"},
        {"id": 4, "name": "소 양념왕갈비", "price": 38000, "image": "/static/images/beef.png"},
    ],
    "식사류": [
        {"id": 5, "name": "전통 함흥냉면(물/비빔)", "price": 11000, "image": "/static/images/noodle.png"},
        {"id": 6, "name": "한우 육회비빔밥", "price": 15000, "image": "/static/images/meal.png"},
        {"id": 7, "name": "차돌 된장찌개", "price": 9000, "image": "/static/images/stew.png"},
        {"id": 8, "name": "공기밥", "price": 1000, "image": "/static/images/meal.png"},
    ],
    "곁들임": [
        {"id": 9, "name": "한우 신선 육회", "price": 28000, "image": "/static/images/beef.png"},
        {"id": 10, "name": "폭탄 계란찜", "price": 5000, "image": "/static/images/egg.png"},
    ],
    "주류/음료": [
        {"id": 11, "name": "소주", "price": 5000, "image": "/static/images/soju.png"},
        {"id": 12, "name": "맥주", "price": 5000, "image": "/static/images/beer.png"},
        {"id": 13, "name": "막걸리", "price": 4000, "image": "/static/images/makgeolli.png"},
        {"id": 14, "name": "콜라", "price": 2000, "image": "/static/images/cola.png"},
        {"id": 15, "name": "사이다", "price": 2000, "image": "/static/images/cider.png"},
    ]
}

# KST (UTC+9) 헬퍼
def get_kst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def get_today_start_kst():
    """오늘 한국 시간 00:00:00에 해당하는 UTC datetime 반환"""
    kst_now = get_kst_now()
    kst_today = kst_now.replace(hour=0, minute=0, second=0, microsecond=0)
    # KST -> UTC 변환 (9시간 차감)
    return kst_today.astimezone(timezone.utc).replace(tzinfo=None)

# 초기화 시점 관리 (persistence용 파일)
RESET_FILE = 'last_reset.txt'

def get_last_reset_time():
    if os.path.exists(RESET_FILE):
        try:
            with open(RESET_FILE, 'r') as f:
                return datetime.fromisoformat(f.read().strip())
        except:
            pass
    return datetime(2000, 1, 1) # 아주 먼 과거

def set_last_reset_time():
    now_utc = datetime.utcnow()
    with open(RESET_FILE, 'w') as f:
        f.write(now_utc.isoformat())
    return now_utc

# 테이블 선점 보관 딕셔너리 { table_id: {'uid': 'abc', 'time': 12345.0} }
active_tables = {}

class OrderWorkflow:
    @staticmethod
    def stage_receive(data):
        """1단계: 주문 접수 - DB 저장 및 주방 전송 (음료는 즉시 서빙 대기 처리)"""
        try:
            order_id = data.get('order_id', f"ORD-{int(time.time()*1000)}")
            session_id = data.get('session_id')
            table_id = int(data['table_id'])
            
            # 테이블 이동 처리
            if session_id:
                active_orders = db.session.query(Order).filter_by(session_id=session_id).filter(Order.status != 'paid').all()
                for o in active_orders:
                    if o.table_id != table_id:
                        print(f"Workflow Migration: Side {session_id} moved from {o.table_id} to {table_id}")
                        o.table_id = table_id

            # 음료 ID 추출 (메뉴 데이터 기준)
            drink_ids = [int(item['id']) for item in menu.get('주류/음료', [])]
            
            food_items = [item for item in data['items'] if int(item['id']) not in drink_ids]
            drink_items = [item for item in data['items'] if int(item['id']) in drink_ids]
            
            created_orders = []

            # 1. 일반 요리 주문 (주방 등록 - pending)
            if food_items:
                food_order_id = order_id if not drink_items else f"{order_id}-F"
                if not db.session.get(Order, food_order_id):
                    food_total = sum(item['price'] * item['quantity'] for item in food_items)
                    new_food_order = Order(
                        id=food_order_id,
                        table_id=table_id,
                        total_price=food_total,
                        status='pending',
                        session_id=session_id
                    )
                    db.session.add(new_food_order)
                    for item in food_items:
                        db.session.add(OrderItem(
                            order_id=food_order_id,
                            menu_id=item['id'],
                            name=item['name'],
                            price=item['price'],
                            quantity=item['quantity']
                        ))
                    created_orders.append(new_food_order)

            # 2. 음료 전용 주문 (바로 카운터 서빙 대기 - ready)
            if drink_items:
                drink_order_id = order_id if not food_items else f"{order_id}-D"
                if not db.session.get(Order, drink_order_id):
                    drink_total = sum(item['price'] * item['quantity'] for item in drink_items)
                    new_drink_order = Order(
                        id=drink_order_id,
                        table_id=table_id,
                        total_price=drink_total,
                        status='ready',
                        session_id=session_id
                    )
                    db.session.add(new_drink_order)
                    for item in drink_items:
                        db.session.add(OrderItem(
                            order_id=drink_order_id,
                            menu_id=item['id'],
                            name=item['name'],
                            price=item['price'],
                            quantity=item['quantity']
                        ))
                    created_orders.append(new_drink_order)

            db.session.commit()

            for order in created_orders:
                print(f"Pipeline Stage 1 [Receive]: {order.id} (Table {table_id}, Status {order.status})")
                socketio.emit('new_order', order.to_dict(), namespace='/')
                
            return bool(created_orders)
        except Exception as e:
            db.session.rollback()
            print(f"Workflow Error [Receive]: {str(e)}")
            return False

    @staticmethod
    def stage_ready(order_id):
        """2단계: 조리 완료 - 상태 업데이트 및 카운터/디스플레이 전송"""
        try:
            order = db.session.get(Order, order_id)
            if order:
                order.status = 'ready'
                db.session.commit()
                print(f"Pipeline Stage 2 [Ready]: {order_id}")
                socketio.emit('order_status_update', order.to_dict(), namespace='/')
                return True
            return False
        except Exception as e:
            db.session.rollback()
            return False

    @staticmethod
    def stage_serve(table_id, session_id=None):
        """3단계: 서빙 완료 - 상태 업데이트 및 디스플레이 전송"""
        try:
            # sessionId가 'legacy-X' 형태면 legacy 주문(session_id=None)으로 취급
            is_legacy = session_id and session_id.startswith('legacy-')
            
            if is_legacy:
                table_id = int(session_id.split('-')[1])
                orders = Order.query.filter_by(table_id=table_id, session_id=None, status='ready').all()
            elif session_id:
                orders = Order.query.filter_by(session_id=session_id, status='ready').all()
            else:
                orders = Order.query.filter_by(table_id=table_id, status='ready').all()
            
            for o in orders:
                o.status = 'served'
            db.session.commit()
            print(f"Pipeline Stage 3 [Serve]: Session {session_id or table_id}")
            socketio.emit('table_status_update', {'table_id': table_id, 'session_id': session_id, 'status': 'served'}, namespace='/')
            return True
        except Exception as e:
            db.session.rollback()
            print(f"Workflow Error [Serve]: {str(e)}")
            return False

    @staticmethod
    def stage_pay(session_id, table_id=None):
        """4단계: 결제 완료 - 최종 DB 저장 및 대시보드 클리어"""
        try:
            # sessionId가 'legacy-X' 형태면 legacy 주문(session_id=None)으로 취급
            is_legacy = session_id and session_id.startswith('legacy-')

            if is_legacy:
                table_id = int(session_id.split('-')[1])
                orders = Order.query.filter_by(table_id=table_id, session_id=None).filter(Order.status != 'paid').all()
            elif session_id:
                orders = Order.query.filter_by(session_id=session_id).filter(Order.status != 'paid').all()
            else:
                orders = Order.query.filter_by(table_id=table_id).filter(Order.status != 'paid').all()
            
            for o in orders:
                if not table_id:
                    table_id = o.table_id
                o.status = 'paid'
                o.paid_at = datetime.utcnow()
            db.session.commit()
            
            # 테이블 선점 해제 (메모리 락 초기화)
            if table_id in active_tables:
                active_tables.pop(table_id, None)

            print(f"Pipeline Stage 4 [Pay]: Session {session_id or table_id}")
            socketio.emit('table_status_update', {'table_id': table_id, 'session_id': session_id, 'status': 'paid'}, namespace='/')
            return True
        except Exception as e:
            db.session.rollback()
            print(f"Workflow Error [Pay]: {str(e)}")
            return False

# 모바일 기기 접속 상태 추적 딕셔너리
client_to_wait_id = {}
wait_id_to_clients = {}

@socketio.on('customer_online')
def handle_customer_online(data):
    try:
        wait_id = str(data.get('wait_id'))
        if wait_id and wait_id != 'null' and wait_id != 'undefined':
            client_to_wait_id[request.sid] = wait_id
            if wait_id not in wait_id_to_clients:
                wait_id_to_clients[wait_id] = set()
            wait_id_to_clients[wait_id].add(request.sid)
            print(f"[소켓 연결] 대기 {wait_id}번 기기 화면 켜짐 (SID={request.sid})")
    except Exception as e:
        print(f"Error in customer_online: {e}")

@socketio.on('disconnect')
def handle_disconnect():
    try:
        sid = request.sid
        if sid in client_to_wait_id:
            wait_id = client_to_wait_id.pop(sid)
            if wait_id in wait_id_to_clients:
                wait_id_to_clients[wait_id].discard(sid)
                if not wait_id_to_clients[wait_id]:
                    del wait_id_to_clients[wait_id]
            print(f"[소켓 종료] 대기 {wait_id}번 기기 화면 꺼짐 (SID={sid})")
    except Exception as e:
        pass

# Socket.IO 이벤트 핸들러
@socketio.on('place_order')
def handle_order(data):
    if OrderWorkflow.stage_receive(data):
        print("Order Processed via Pipeline")
    else:
        emit('order_error', {'message': '주문 처리 중 오류 발생'})

@socketio.on('set_ready')
def handle_ready(data):
    OrderWorkflow.stage_ready(data.get('order_id'))

@socketio.on('set_served')
def handle_served(data):
    OrderWorkflow.stage_serve(data.get('table_id'), data.get('session_id'))

@socketio.on('set_paid')
def handle_paid(data):
    OrderWorkflow.stage_pay(data.get('session_id'), data.get('table_id'))

# HTTP 라우트
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/customer/<int:table_id>')
def customer_view(table_id):
    if 'uid' not in session or len(str(session['uid'])) > 3:
        session['uid'] = str(random.randint(100, 999))
    uid = session['uid']

    # 1. DB 점검: 이 테이블에 현재 결제되지 않은(진행 중인) 다른 사람의 주문이 있는지 확인
    active_order = db.session.query(Order).filter_by(table_id=table_id).filter(Order.status != 'paid').first()
    
    if active_order:
        # 다른 사람의 세션 아이디로 주문이 진행중이라면 차단
        if active_order.session_id and active_order.session_id != uid:
            return render_template('locked.html', table_id=table_id)
        # 내 주문이면 무사 통과, 락 갱신
        active_tables[table_id] = {'uid': uid, 'time': time.time()}
    else:
        # 2. 빈 테이블일 때: 과거 점유자가 주문을 하지 않고 나갔다면, 즉시 새로운 기기(세션)의 접속을 허용합니다(무단 점유 방지)
        active_tables[table_id] = {'uid': uid, 'time': time.time()}

    return render_template('customer.html', table_id=table_id, menu=menu, session_id=uid)

@app.route('/kitchen')
def kitchen_view():
    return render_template('kitchen.html')

@app.route('/counter')
def counter_view():
    return render_template('counter.html')

@app.route('/display')
def display_view():
    return render_template('display.html')

@app.route('/waiting', strict_slashes=False)
def waiting_view():
    return render_template('waiting.html')

@app.route('/qr-print', strict_slashes=False)
def qr_print_view():
    # 이제 수동으로 주소를 바꿀 필요 없이, 현재 접속한 도메인(Host)을 자동으로 감지합니다.
    host_url = request.host_url
    return render_template('qr_print.html', host_url=host_url)

# 간편 주소 지원 (Redirect 포함)
@app.route('/qr', strict_slashes=False)
def qr_short_view():
    return redirect(url_for('qr_print_view'))

@app.route('/stats')
def stats_view():
    return render_template('stats.html')

@app.route('/api/orders')
def get_orders():
    try:
        active_orders = db.session.query(Order).filter(Order.status != 'paid').all()
        return jsonify([o.to_dict() for o in active_orders])
    except Exception as e:
        print(f"Error in get_orders API: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats')
def get_stats():
    try:
        # 기준 시점 = MAX(오늘 자정 KST, 마지막 수동 초기화 시점)
        today_start = get_today_start_kst()
        last_reset = get_last_reset_time()
        window_start = max(today_start, last_reset)

        # 일간 매출 합계 (필터 적용)
        daily_sales = db.session.query(func.sum(Order.total_price)).filter(
            Order.paid_at >= window_start,
            Order.status == 'paid'
        ).scalar() or 0
        
        # 인기 메뉴 (필터 적용)
        best_menu = db.session.query(
            OrderItem.name, func.sum(OrderItem.quantity).label('total_qty')
        ).join(Order).filter(
            Order.paid_at >= window_start,
            Order.status == 'paid'
        ).group_by(OrderItem.name).order_by(desc('total_qty')).limit(5).all()
        
        return jsonify({
            'daily_sales': daily_sales,
            'best_menu': [{'name': m[0], 'count': m[1]} for m in best_menu]
        })
    except Exception as e:
        print(f"Error in get_stats API: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats/reset', methods=['POST'])
def reset_stats():
    try:
        set_last_reset_time()
        print(f"[Info] Daily stats reset at {datetime.utcnow()}")
        return jsonify({"status": "success", "message": "매출 통계가 초기화되었습니다."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 대기열 API
@app.route('/api/waiting', methods=['POST'])
def register_waiting():
    try:
        data = request.json
        phone = data['phone']
        
        # [핵심 로직] 동일한 번호로 이미 대기 중인 건이 있다면 자동으로 취소 처리 (재등록 허용)
        today_start = get_today_start_kst()
        existing_waiting = db.session.query(Waiting).filter(
            Waiting.phone == phone,
            Waiting.status == 'waiting',
            Waiting.created_at >= today_start
        ).first()

        if existing_waiting:
            existing_waiting.status = 'cancelled'
            db.session.commit()
            print(f"[Info] Duplicate phone ({phone}) re-registered. Old entry ({existing_waiting.id}) cancelled.")

        # 3자리 난수 대기 번호 생성
        new_wait = Waiting(
            phone=phone,
            people=int(data['people']),
            waiting_no=random.randint(100, 999),
            status='waiting'
        )
        db.session.add(new_wait)
        db.session.commit()
        
        # 실시간 업데이트 (카운터용)
        socketio.emit('waiting_update', namespace='/')
        
        return jsonify({"status": "success", "wait_id": new_wait.id, "waiting_no": new_wait.waiting_no})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/waiting/status/<int:wait_id>')
def get_waiting_status(wait_id):
    try:
        wait = db.session.get(Waiting, wait_id)
        if not wait: return jsonify({"status": "not_found"}), 404
        
        today_start = get_today_start_kst()
        if wait.created_at < today_start:
            return jsonify({"status": "expired"}), 200
        
        if wait.status == 'entered':
            # 입장 완료 후 30분 초과 시 만료 처리 (Stale Session 방지)
            now = datetime.utcnow()
            diff = now - (wait.updated_at or wait.created_at)
            if diff.total_seconds() > 1800: # 30분이 지난 경우
                return jsonify({"status": "expired"}), 200
            
        if wait.status != 'waiting': 
            return jsonify({"status": wait.status, "waiting_no": wait.waiting_no}), 200
        
        # 내 앞에 몇 명이나 있나? (id 순서대로 체크)
        rank = db.session.query(Waiting).filter(
            Waiting.status == 'waiting',
            Waiting.id < wait_id,
            Waiting.created_at >= today_start
        ).count()
        
        kst_created = wait.created_at + timedelta(hours=9)
        ampm = "오후" if kst_created.hour >= 12 else "오전"
        hour12 = kst_created.hour % 12 or 12
        created_str = f"{ampm} {hour12}:{kst_created.minute:02d}:{kst_created.second:02d}"

        return jsonify({
            "status": "waiting",
            "wait_id": wait.id,
            "waiting_no": wait.waiting_no,
            "rank": rank,
            "created_at_fixed": created_str
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/waiting/list')
def get_waiting_list():
    try:
        active_waiting = db.session.query(Waiting).filter(Waiting.status == 'waiting').all()
        return jsonify([w.to_dict() for w in active_waiting])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/waiting/enter/<int:wait_id>', methods=['POST'])
def enter_waiting(wait_id):
    try:
        wait = db.session.get(Waiting, wait_id)
        if wait:
            wait.status = 'entered'
            wait.updated_at = datetime.utcnow()
            db.session.commit()
            
            # 브라우저를 닫은 손님인지 확인 (화면이 켜져있으면 SMS 생략)
            is_client_online = str(wait_id) in wait_id_to_clients
            if is_client_online:
                print(f"[알림톡 스킵] {wait.waiting_no}번({wait.phone}) 손님은 현재 화면을 켜두고 있어 소켓으로만 입장 신호를 보냅니다.")
            else:
                enter_msg = f"[수라골] 대기 번호 {wait.waiting_no}번 손님! 지금 즉시 식당으로 입장해주세요!\n\n▶ 입장권 열기(매장 직원 제시용)\nhttps://wang.chicvill.store/waiting"
                try:
                    messenger.send_sms(wait.phone, enter_msg)
                    print(f"[알림톡] {wait.phone} 님에게 입장 호출 발송 완료")
                except Exception as e:
                    print(f"[알림톡] 발송 실패: {e}")
            
            # 알림 로직 (대기 순서가 당겨진 뒷사람들에게 안내)
            trigger_notifications()
            
            # 실시간 업데이트 (카운터 목록 제어용)
            socketio.emit('waiting_update', namespace='/')
            
            # 특정 손님 핸드폰에 전송할 "입장 신호" (보안을 위해 id 포함)
            socketio.emit('waiting_status_update', {
                'wait_id': wait_id,
                'status': 'entered'
            }, namespace='/')
            
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "Not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def trigger_notifications():
    """대기 순서가 3번 이내인 사람들에게 알림 전송"""
    try:
        waiting_list = db.session.query(Waiting).filter(Waiting.status == 'waiting').order_by(Waiting.id).all()
        for i, w in enumerate(waiting_list):
            if i < 3 and not w.notified:
                w.notified = True
                
                is_client_online = str(w.id) in wait_id_to_clients
                if is_client_online:
                    print(f"[알림톡 스킵] 대기 {w.waiting_no}번({w.phone}) - 3팀 이내 진입, 현재 접속 중")
                else:
                    remains = i
                    msg = f"[수라골] 대기 번호 {w.waiting_no}번 손님! 내 앞에 대기 {remains}팀 남았습니다. 매장 근처에서 준비해주세요!\n\n▶ 내 대기 상태 보기\nhttps://wang.chicvill.store/waiting"
                    try:
                        messenger.send_sms(w.phone, msg)
                        print(f"[알림톡] {w.phone} 님에게 대기 3팀 이내 경고 발송 완료")
                    except Exception as sms_e:
                        print(f"[알림톡] 발송 실패: {sms_e}")
                        
                db.session.commit()
    except Exception as e:
        print(f"[Error] trigger_notifications: {e}")

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response

if __name__ == '__main__':
    # 서버 실행 시 도메인 주소 안내 (보안 인증 적용)
    port = int(os.environ.get('PORT', 8888))
    domain = "wang.chicvill.store"
    
    print("\n" + "="*60)
    print(" [서버 시작] 수라골 참숯갈비 통합 관리 시스템 (도메인 모드)")
    print(f" * 카운터 주소: http://localhost:{port}/counter")
    print(f" * 고객 대기 주소: https://{domain}/waiting")
    print(f" * QR 출력 페이지: https://{domain}/qr-print")
    print("="*60 + "\n")
    print("[상상] 보안 터널(Cloudflare)을 통해 'https' 보안 연결이 활성화되었습니다.")
    
    # SSL 설정을 제외하고 순수 HTTP로 실행 (터널이 HTTPS 처리를 함)
    socketio.run(app, debug=True, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
