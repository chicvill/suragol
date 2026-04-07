from app import app, db
from models import Store

with app.app_context():
    # '왕궁'이라는 이름이 포함된 매장을 찾아 테이블 수를 6으로 수정합니다.
    s = Store.query.filter(Store.name.contains('왕궁')).first()
    if s:
        s.tables_count = 6
        db.session.commit()
        print(f"✅ [처리 완료] '{s.name}'의 테이블 수가 {s.tables_count}개로 수정되었습니다.")
    else:
        print("❌ [오류] 해당 매장을 찾을 수 없습니다.")
