import os
from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        # 추가할 컬럼들과 그 타입 정의
        new_columns = [
            ("is_public", "BOOLEAN DEFAULT FALSE"),
            ("signature_owner", "TEXT"),
            ("signature_partner", "TEXT"),
            ("theme_color", "VARCHAR(20) DEFAULT '#3b82f6'"),
            ("contact_phone", "VARCHAR(50)"),
            ("point_ratio", "FLOAT DEFAULT 0.0"),
            ("waiting_sms_no", "VARCHAR(50)"),
            ("business_type", "VARCHAR(50)"),
            ("business_item", "VARCHAR(100)"),
            ("business_email", "VARCHAR(100)")
        ]
        
        for col_name, col_type in new_columns:
            try:
                # PostgreSQL/SQLite 모두 호환되는 ALTER TABLE 문
                query = text(f"ALTER TABLE stores ADD COLUMN {col_name} {col_type}")
                db.session.execute(query)
                print(f"✅ 컬럼 추가 성공: {col_name}")
            except Exception as e:
                # 이미 컬럼이 존재하는 경우 에러가 나므로 무시
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    print(f"ℹ️ 이미 존재함: {col_name}")
                else:
                    print(f"❌ {col_name} 추가 중 오류: {e}")
        
        db.session.commit()
        print("🚀 데이터베이스 마이그레이션 완료!")

if __name__ == "__main__":
    migrate()
