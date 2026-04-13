from app import app, db
from models import Order, OrderItem, ServiceRequest, Waiting
from sqlalchemy import text

def reset_order_data():
    with app.app_context():
        print("🛠️ [주문 데이터 초기화 시작]")
        try:
            # PostgreSQL의 경우 CASCADE 권장, SQLite는 지원 안함
            is_postgres = "postgresql" in app.config['SQLALCHEMY_DATABASE_URI']
            
            if is_postgres:
                # 외래 키 제약 조건 해결을 위해 TRUNCATE ... CASCADE 사용
                db.session.execute(text("TRUNCATE TABLE order_items CASCADE;"))
                db.session.execute(text("TRUNCATE TABLE orders CASCADE;"))
                db.session.execute(text("TRUNCATE TABLE service_requests CASCADE;"))
                db.session.execute(text("TRUNCATE TABLE waiting CASCADE;"))
                print("✅ [PostgreSQL] 모든 주문, 서비스 요청, 웨이팅 내역을 초기화했습니다.")
            else:
                # SQLite 등 일반 삭제
                db.session.query(OrderItem).delete()
                db.session.query(Order).delete()
                db.session.query(ServiceRequest).delete()
                db.session.query(Waiting).delete()
                print("✅ [SQLite] 모든 주문 및 웨이팅 정보를 삭제했습니다.")
                
            db.session.commit()
            print("🚀 [완료] DB 초기화가 성공적으로 끝났습니다.")
        except Exception as e:
            db.session.rollback()
            print(f"❌ [에러] 초기화 중 문제가 발생했습니다: {e}")

if __name__ == '__main__':
    reset_order_data()
