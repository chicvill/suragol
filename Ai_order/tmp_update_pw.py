from app import app, db
from models import User
from werkzeug.security import generate_password_hash

def change_pw():
    with app.app_context():
        user = User.query.filter_by(username='admin').first()
        if user:
            user.password = generate_password_hash('1111')
            db.session.commit()
            print("✅ admin 비밀번호가 '1111'로 변경되었습니다.")
        else:
            print("❌ 'admin' 사용자를 찾을 수 없습니다.")

if __name__ == "__main__":
    change_pw()
