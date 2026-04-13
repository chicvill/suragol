import shutil
import os
import json
from app import app, db, Store

# 이미지 경로 정의
source_dir = r"C:\Users\USER\.gemini\antigravity\brain\70284fa0-ed2b-4e2b-826f-707ab851e70d"
target_dir = r"c:\Users\USER\Dev\FreeOrder\static\images"

images = {
    "pepperoni": "seoknam_pizza_pepperoni_1775545339400.png",
    "combination": "seoknam_pizza_combination_1775545365969.png",
    "sweetpotato": "seoknam_pizza_sweetpotato_1775545381454.png"
}

# 1. 이미지 복사
print("🚀 [이미지 복사 중...]")
for key, filename in images.items():
    src = os.path.join(source_dir, filename)
    dst = os.path.join(target_dir, filename)
    if os.path.exists(src):
        shutil.copy(src, dst)
        print(f"✅ {filename} 복사 완료")
    else:
        print(f"⚠️ {filename} 파일을 찾을 수 없습니다.")

# 2. 데이터베이스 등록
print("\n🏗️ [석남피자 인스턴스 구축 중...]")
with app.app_context():
    # 기존 데이터 삭제 (업데이트 목적)
    existing = Store.query.get('seoknam-pizza')
    if existing:
        db.session.delete(existing)
        db.session.commit()
    
    menu_data = {
        "피자 (Pizza)": [
            {"name": "석남 시그니처 페퍼로니", "price": 18900, "image": f"/static/images/{images['pepperoni']}"},
            {"name": "듬뿍 콤비네이션", "price": 19900, "image": f"/static/images/{images['combination']}"},
            {"name": "골든 고구마 무스", "price": 20900, "image": f"/static/images/{images['sweetpotato']}"}
        ],
        "사이드 (Side)": [
            {"name": "오븐 치즈 파스타", "price": 7500, "image": ""},
            {"name": "핫윙 (6pcs)", "price": 6000, "image": ""}
        ],
        "음료 (Drink)": [
            {"name": "콜라 (1.25L)", "price": 2500, "image": ""},
            {"name": "제로 콜라 (1.25L)", "price": 2500, "image": ""}
        ]
    }

    new_store = Store(
        id='seoknam-pizza',
        name='석남피자',
        tables_count=15,
        menu_data=menu_data,
        status='active',
        payment_status='paid'
    )
    
    db.session.add(new_store)
    db.session.commit()
    print("✅ [설치 완료] 석남피자(seoknam-pizza)가 정식 등록되었습니다.")
