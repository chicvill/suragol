import uuid
import random
from datetime import datetime, timedelta
from flask_socketio import join_room
from models import db, Order, OrderItem, Customer, PointTransaction, Store

def register_socketio_events(socketio):
    @socketio.on('join')
    def on_join(data):
        sid = data.get('store_id')
        if sid:
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
            depositor_name = data.get('depositor_name')

            if not items:
                print("⚠️ [주문 오류] 빈 주문 목록이 전송되었습니다.")
                return

            order_id = str(uuid.uuid4())
            order_no = str(random.randint(1000, 9999)) # 화면 노출용 4자리 난수 주문번호
            new_order = Order(id=order_id, order_no=order_no, store_id=slug, table_id=table_id, session_id=session_id, total_price=total_price, phone=phone, depositor_name=depositor_name)
            db.session.add(new_order)
            
            for item in items:
                # menu_id가 누락되었을 경우 0으로 대체 (AI 초기 메뉴 등)
                m_id = item.get('id', 0)
                oi = OrderItem(order_id=order_id, menu_id=m_id, name=item['name'], price=item['price'], quantity=item['quantity'])
                db.session.add(oi)
            
            db.session.commit()
            print(f"✅ [주문 성공] {slug} 테이블 {table_id} - 주문번호 {order_no}")
            
            # 주문을 넣은 손님에게 성공 알림과 번호 전송
            from flask import request
            store_obj = db.session.get(Store, slug)
            socketio.emit('order_success', {
                'order_no': order_no, 
                'depositor_name': depositor_name or "",
                'total_price': total_price,
                'bank_name': store_obj.bank_name if store_obj else "",
                'account_no': store_obj.account_no if store_obj else "",
                'account_holder': store_obj.account_holder if store_obj else "",
                'store_name': store_obj.name if store_obj else slug
            }, room=request.sid)

            socketio.emit('new_order', new_order.to_dict(), room=slug)
        except Exception as e:
            db.session.rollback()
            err_msg = str(e)
            print(f"❌ [주문 처리 오류] {err_msg}")
            socketio.emit('order_error', {'message': f'주문 처리 중 서버 오류가 발생했습니다: {err_msg}'})

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
                
                # [수정] 포인트 적립률 동적화 (사장님이 0으로 설정하면 적립 안 함, 초기 미설정 시 기본 1%)
                store_for_ratio = db.session.get(Store, slug)
                ratio = store_for_ratio.point_ratio if (store_for_ratio and store_for_ratio.point_ratio is not None) else 0.01
                acc_amount = int(total_sum * ratio)
                
                cust.visit_count += 1
                cust.total_spent += total_sum
                if acc_amount > 0:
                    cust.points += acc_amount
                    cust.last_accumulation_at = datetime.utcnow()
                    db.session.add(PointTransaction(customer_id=cust.id, store_id=slug, amount=acc_amount, description="식비 적립"))
        
        for o in orders:
            o.status = 'paid'
            o.paid_at = datetime.utcnow()
        
        db.session.commit()
        socketio.emit('table_status_update', {'store_id': slug, 'session_id': sid, 'table_id': tid, 'status': 'paid'}, room=slug)

    @socketio.on('cancel_order')
    def on_cancel_order(data):
        try:
            oid = data.get('order_id')
            if not oid: return
            order = db.session.get(Order, oid)
            if order:
                order.status = 'cancelled'
                order.total_price = 0
                # 모든 아이템도 취소 처리
                for item in order.items:
                    item.status = 'cancelled'
                db.session.commit()
                # 상태 변경 알림 (동적으로 삭제되도록)
                socketio.emit('order_status_update', order.to_dict(), room=order.store_id)
                print(f"✅ [취소] 주문 {oid} 전체 취소됨")
        except Exception as e:
            db.session.rollback()
            print(f"❌ [취소 오류] 주문 취소 중 에러: {e}")

    @socketio.on('cancel_order_item')
    def on_cancel_order_item(data):
        try:
            item_id = data.get('item_id')
            if not item_id: return
            item = db.session.get(OrderItem, item_id)
            if item:
                order = item.order
                item.status = 'cancelled'
                
                # 주문 총액 재계산
                active_items = [i for i in order.items if i.status != 'cancelled']
                order.total_price = sum(i.price * i.quantity for i in active_items)
                
                # 만약 남은 아이템이 하나도 없으면 주문 자체를 취소 처리
                if not active_items:
                    order.status = 'cancelled'
                
                db.session.commit()
                socketio.emit('order_status_update', order.to_dict(), room=order.store_id)
                print(f"✅ [일부 취소] 아이템 {item_id} 취소됨, 주문 {order.id} 총액 갱신")
        except Exception as e:
            db.session.rollback()
            print(f"❌ [일부 취소 오류] 아이템 취소 중 에러: {e}")
