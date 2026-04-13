from app import app, db
from sqlalchemy import text

def add_email_field():
    with app.app_context():
        print("--- 이메일 컬럼 추가 작업 시작 ---")
        try:
            # SQL 직접 실행하여 컬럼 추가
            db.session.execute(text('ALTER TABLE stores ADD COLUMN business_email VARCHAR(100)'))
            db.session.commit()
            print("[성공] 'business_email' 컬럼이 데이터베이스에 추가되었습니다.")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("[알림] 이메일 컬럼이 이미 존재합니다.")
            else:
                print(f"[오류] 작업 중 문제가 발생했습니다: {e}")
        print("--- 작업 완료 ---")

if __name__ == "__main__":
    add_email_field()
