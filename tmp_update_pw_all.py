import os
from app import app, db
from models import User
from werkzeug.security import generate_password_hash

def update_all_passwords():
    with app.app_context():
        new_pw = "1212"
        hashed_pw = generate_password_hash(new_pw)
        
        users = User.query.all()
        count = 0
        for user in users:
            user.password = hashed_pw
            count += 1
        
        db.session.commit()
        print(f"✅ [성공] 총 {count}명의 사용자 비밀번호를 '{new_pw}'로 변경했습니다.")

if __name__ == "__main__":
    update_all_passwords()
