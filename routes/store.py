import uuid
import threading
from datetime import datetime, timedelta
from flask import request, session, render_template, redirect, url_for, jsonify
from sqlalchemy import func, desc
from models import db, Store, Order, OrderItem, Customer, ServiceRequest, Waiting
from extensions import socketio

# 필요하다면 상대경로/절대경로 맞게 MQutils 임포트
from MQutils import (
    store_access_required, login_required, 
    get_ai_operation_insight, get_ai_recommended_menu, 
    send_waiting_sms, check_nearby_waiting
)

def init_store_routes(app):
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
            
        # [수정] 통합 세션(3분 타임아웃)과 분리하여, 손님 장바구니 전용 영구 쿠키(uid) 사용
        uid = request.cookies.get('customer_uid')
        if not uid:
            uid = str(uuid.uuid4())[:12]
            
        from flask import make_response
        resp = make_response(render_template('customer.html', store=store, table_id=table_id, session_id=uid))
        # 12시간 동안 장바구니/테이블 세션 유지 (3분 보안 세션 초기화 버그 완전 차단)
        resp.set_cookie('customer_uid', uid, max_age=60*60*12)
        return resp

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
    @login_required  # [수정] staff_required였으나, 편의상 로그인한 담당 권한자로만 완화
    def admin_qr_print_view(slug):
        store = db.session.get(Store, slug)
        if not store: return "매장을 찾을 수 없습니다.", 404
        
        # [핵심] 현재 접속 중인 도메인을 자동으로 감지하여 QR 주소로 사용
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
        # [글로벌] 매장 타임존 동기화
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            pass
            
        store = db.session.get(Store, slug)
        try:
            tz = ZoneInfo(store.timezone if store and store.timezone else 'Asia/Seoul')
        except Exception:
            from datetime import timezone as dt_timezone, timedelta
            tz = dt_timezone(timedelta(hours=9))
            
        now_local = datetime.now(tz)
        
        if period == 'week':
            local_start = (now_local - timedelta(days=now_local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'month':
            local_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == 'year':
            local_start = now_local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            local_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            
        from datetime import timezone
        start_date = local_start.astimezone(timezone.utc).replace(tzinfo=None)
        
        # [수정] 통계 리셋 기준점 반영
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
        """[수정] 실제 데이터 변조 없이 리셋 기준시각을 저장하는 방식화"""
        store = db.session.get(Store, slug)
        if not store:
            return jsonify({'status': 'error', 'message': '매장을 찾을 수 없습니다.'}), 404
        
        # [긴급 조치] 통계 리셋 시 꼬인 주문 데이터(전체)를 함께 삭제하여 유령 주문 문제 해결
        Order.query.filter_by(store_id=slug).delete()
        
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
    # 웨이팅(예약) 시스템 API
    # ---------------------------------------------------------
    @app.route('/api/<slug>/waiting', methods=['POST'])
    def api_create_waiting(slug):
        data = request.json
        phone = data.get('phone', '010-0000-0000')
        people = int(data.get('people', 1))
        
        # [글로벌] 웨이팅 번호 초기화 기준을 각 매장 현지 시간 자정으로 설정
        store = db.session.get(Store, slug)
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(store.timezone if store and store.timezone else 'Asia/Seoul')
        except Exception:
            from datetime import timezone as dt_timezone, timedelta
            tz = dt_timezone(timedelta(hours=9))
            
        now_local = datetime.now(tz)
        local_today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        
        from datetime import timezone
        today_start_utc = local_today_start.astimezone(timezone.utc).replace(tzinfo=None)
        
        today_count = Waiting.query.filter_by(store_id=slug).filter(
            Waiting.created_at >= today_start_utc
        ).count()
        
        new_wait = Waiting(store_id=slug, phone=phone, people=people, waiting_no=today_count+1)
        db.session.add(new_wait)
        db.session.commit()
        
        socketio.emit('waiting_update', room=slug)
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
        
        rank = Waiting.query.filter_by(store_id=slug, status='waiting').filter(Waiting.created_at < w.created_at).count()
        res = w.to_dict()
        res['rank'] = rank
        res['created_at_fixed'] = w.created_at.strftime('%H:%M')
        return jsonify(res)

    @app.route('/api/<slug>/waiting/notify/<int:wait_id>', methods=['POST'])
    @store_access_required
    def api_notify_waiting_manual(slug, wait_id):
        w = db.session.get(Waiting, wait_id)
        if w and w.store_id == slug:
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
            socketio.emit('waiting_status_update', {'wait_id': wait_id, 'status': 'entered'}, room=slug)
            socketio.emit('waiting_update', room=slug)
            threading.Thread(target=send_waiting_sms, args=(app, wait_id, 'enter')).start()
            check_nearby_waiting(app, slug)
            return jsonify({'status': 'success'})
        return jsonify({'error': 'Not found', 'message': '대기 정보를 찾을 수 없습니다.'}), 404

    @app.route('/api/<slug>/waiting/cancel/<int:wait_id>', methods=['POST'])
    def api_cancel_waiting(slug, wait_id):
        w = db.session.get(Waiting, wait_id)
        if w and w.store_id == slug:
            w.status = 'canceled'
            db.session.commit()
            socketio.emit('waiting_status_update', {'wait_id': wait_id, 'status': 'canceled'}, room=slug)
            socketio.emit('waiting_update', room=slug)
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
            if cust.last_accumulation_at and cust.last_accumulation_at < datetime.utcnow() - timedelta(days=365):
                cust.points = 0
                db.session.commit()
        return jsonify(cust.to_dict())

    # ---------------------------------------------------------
    # 주문 관리 및 결제 API (카운터 연동)
    # ---------------------------------------------------------
    @app.route('/api/<slug>/table/<int:table_id>/pay', methods=['POST'])
    def api_table_pay_all(slug, table_id):
        """테이블의 모든 미결제 주문을 '결제완료' 처리하고 퇴실시킵니다."""
        orders = Order.query.filter_by(store_id=slug, table_id=table_id).filter(Order.status != 'paid').all()
        now = datetime.utcnow()
        for o in orders:
            o.status = 'paid'
            o.paid_at = now
        db.session.commit()
        socketio.emit('table_status_update', {'table_id': table_id, 'status': 'paid'}, room=slug)
        return jsonify({'status': 'success', 'count': len(orders)})

    @app.route('/api/order/<order_id>/cancel', methods=['POST'])
    def api_cancel_order(order_id):
        """특정 주문을 강제 취소 처리합니다."""
        o = db.session.get(Order, order_id)
        if o:
            o.status = 'cancelled'
            db.session.commit()
            socketio.emit('order_status_update', {'id': order_id, 'status': 'cancelled'}, room=o.store_id)
            return jsonify({'status': 'success'})
        return jsonify({'error': 'Not found'}), 404

    @app.route('/api/order/<order_id>/prepaid', methods=['POST'])
    def api_prepaid_order(order_id):
        """주문을 선결제 완료 상태로 변경합니다."""
        o = db.session.get(Order, order_id)
        if o:
            o.is_prepaid = True
            db.session.commit()
            socketio.emit('order_status_update', {'id': order_id, 'is_prepaid': True}, room=o.store_id)
            return jsonify({'status': 'success'})
        return jsonify({'error': 'Not found'}), 404
