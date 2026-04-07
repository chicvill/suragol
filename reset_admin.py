from app import app, db, User
from werkzeug.security import generate_password_hash
import sys

def reset_admin_password():
    with app.app_context():
        print("--- [시작] 관리자 계정 초기화 작업 ---")
        
        # 1. 기존 'admin' 계정 찾기
        admin_user = User.query.filter_by(username='admin').first()
        
        if admin_user:
            print(f"🔍 기존 관리자 계정 발견: {admin_user.username}")
            admin_user.password = generate_password_hash('1111')
            admin_user.role = 'admin'
            admin_user.is_approved = True
            db.session.commit()
            print("✅ [성공] 기존 관리자 계정의 비밀번호를 '1111'로 초기화했습니다.")
        else:
            print("🔍 관리자 계정이 존재하지 않습니다. 새 계정을 생성합니다...")
            # 2. 계정이 없으면 새로 생성
            new_admin = User(
                username='admin',
                password=generate_password_hash('1111'),
                role='admin',
                full_name='최고관리자',
                is_approved=True
            )
            db.session.add(new_admin)
            try:
                db.session.commit()
                print("✅ [성공] 새로운 관리자 계정을 생성했습니다 (ID: admin, PW: 1111)")
            except Exception as e:
                db.session.rollback()
                print(f"❌ [실패] 관리자 계정 생성 중 오류 발생: {e}")
        
        # 3. 혹시 'admin' 역할을 가진 다른 계정들도 모두 체크하여 일관성 유지 (선택사항)
        print("--- [완료] 작업이 종료되었습니다. ---")

if __name__ == "__main__":
    reset_admin_password()
