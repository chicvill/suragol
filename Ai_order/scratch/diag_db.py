import sys
import os
sys.path.append(os.getcwd())
from app import app, db
from models import Order, Store

with app.app_context():
    # 1. 매장 확인
    stores = Store.query.all()
    print(f"--- 매장 목록 ({len(stores)}개) ---")
    for s in stores:
        print(f"ID: {s.id}, Name: {s.name}")

    # 2. 미결제 주문 전수 조사
    active_orders = Order.query.filter(Order.status != 'paid').all()
    print(f"\n--- 미결제 주문 목록 ({len(active_orders)}개) ---")
    for o in active_orders:
        print(f"Store: {o.store_id}, Table: {o.table_id}, Status: {o.status}, Total: {o.total_price}, ID: {o.id}")

    # 3. 특정 매장(sucknampiza) 집중 점검
    target = 'sucknampiza'
    target_orders = Order.query.filter_by(store_id=target).filter(Order.status != 'paid').all()
    print(f"\n--- [{target}] 매장 상세 점검 ---")
    if not target_orders:
        print("미결제 주문이 없습니다. (이미 결제되었거나 다른 ID로 들어가 있음)")
    else:
        for o in target_orders:
             print(f"테이블 {o.table_id}: {o.status} ({o.total_price}원) - {len(o.items)}개 품목")
