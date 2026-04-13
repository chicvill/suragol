from app import app, db
from sqlalchemy import text
import sys

def update_db():
    print("🚀 DB 구조 업데이트를 시작합니다...")
    with app.app_context():
        try:
            # 1. cash_receipt_type 컬럼 추가 시도
            try:
                db.session.execute(text("ALTER TABLE orders ADD COLUMN cash_receipt_type VARCHAR(20)"))
                db.session.commit()
                print("✅ cash_receipt_type 컬럼이 추가되었습니다.")
            except Exception as e:
                db.session.rollback()
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print("ℹ️ cash_receipt_type 컬럼이 이미 존재합니다.")
                else:
                    print(f"⚠️ 컬럼 추가 중 오류 발생: {e}")

            # 2. cash_receipt_number 컬럼 추가 시도
            try:
                db.session.execute(text("ALTER TABLE orders ADD COLUMN cash_receipt_number VARCHAR(20)"))
                db.session.commit()
                print("✅ cash_receipt_number 컬럼이 추가되었습니다.")
            except Exception as e:
                db.session.rollback()
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print("ℹ️ cash_receipt_number 컬럼이 이미 존재합니다.")
                else:
                    print(f"⚠️ 컬럼 추가 중 오류 발생: {e}")

            print("\n🎉 DB 업데이트 프로세스가 완료되었습니다!")
            
        except Exception as global_e:
            print(f"❌ 예기치 못한 전체 오류: {global_e}")
            sys.exit(1)

if __name__ == "__main__":
    update_db()
