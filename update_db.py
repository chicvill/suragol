import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# DB 연결 정보 설정
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///suragol.db')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print(f"Connecting to: {DATABASE_URL}")
engine = create_engine(DATABASE_URL)

# 추가할 컬럼 목록 (테이블명, 컬럼명, 타입)
new_columns = [
    ("stores", "business_no", "VARCHAR(20)"),
    ("stores", "ceo_name", "VARCHAR(50)"),
    ("stores", "business_type", "VARCHAR(50)"),
    ("stores", "business_item", "VARCHAR(100)")
]

def update_schema():
    with engine.connect() as conn:
        print("\n--- DB 스키마 업데이트 시작 ---")
        for table, col, col_type in new_columns:
            try:
                # ALTER TABLE 명령 실행
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                # SQLAlchemy 2.0 이상에서는 commit이 필요할 수 있음
                try:
                    conn.commit()
                except:
                    pass
                print(f"[성공] {table} 테이블에 {col} 컬럼이 추가되었습니다.")
            except Exception as e:
                err_msg = str(e).lower()
                if "already exists" in err_msg or "duplicate column" in err_msg:
                    print(f"[건너뜀] {table}.{col} 컬럼이 이미 존재합니다.")
                else:
                    print(f"[오류] {col} 추가 중 문제 발생: {e}")
        print("\n--- 업데이트 완료! ---")

if __name__ == "__main__":
    update_schema()
