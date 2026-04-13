from app import app, db
from sqlalchemy import text

def patch_performance_schema():
    with app.app_context():
        print("--- 직원 실적 분석용 DB 패치 시작 ---")
        try:
            # 업소 테이블에 관리 직원(User) ID 연결용 컬럼 추가
            db.session.execute(text('ALTER TABLE stores ADD COLUMN recommended_by INTEGER REFERENCES users(id)'))
            db.session.commit()
            print("[성공] 'recommended_by' 컬럼이 추가되었습니다.")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("[알림] 컬럼이 이미 존재합니다.")
            else:
                print(f"[오류] 패치 중 문제 발생: {e}")
        print("--- 패치 완료 ---")

if __name__ == "__main__":
    patch_performance_schema()
