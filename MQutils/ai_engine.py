import random

# ---------------------------------------------------------
# AI 메뉴 추천 프리셋 (업종별 자동 생성용)
# ---------------------------------------------------------
AI_MENU_PRESETS = {
    '커피/카페': {
        '☕ 에스프레소/커피': [
            {'name': '아메리카노 (HOT/ICE)', 'price': 4500, 'image': 'https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=500&q=80'},
            {'name': '카페라떼', 'price': 5000, 'image': 'https://images.unsplash.com/photo-1541167760496-1628856ab772?w=500&q=80'},
            {'name': '바닐라라떼', 'price': 5500, 'image': 'https://images.unsplash.com/photo-1461023232487-0b1368421876?w=500&q=80'}
        ],
        '🍰 디저트': [
            {'name': '전통 다과 세트', 'price': 7500, 'image': 'https://images.unsplash.com/photo-1558961363-fa8fdf82db35?w=500&q=80'},
            {'name': '치즈 케이크', 'price': 6500, 'image': 'https://images.unsplash.com/photo-1533134242443-d4fd215305ad?w=500&q=80'}
        ]
    },
    '한식/식당': {
        '🥘 식사류': [
            {'name': '전통 비빔밥', 'price': 9000, 'image': 'https://images.unsplash.com/photo-1590301157890-4810ed352733?w=500&q=80'},
            {'name': '김치찌개 정식', 'price': 8500, 'image': 'https://images.unsplash.com/photo-1583224964978-2257b960c3d3?w=500&q=80'},
            {'name': '뚝배기 불고기', 'price': 11000, 'image': 'https://images.unsplash.com/photo-1624462966581-20a282492162?w=500&q=80'}
        ]
    },
    '중식/차이니즈': {
        '🍜 면/식사류': [
            {'name': '명품 짜장면', 'price': 7000, 'image': 'https://images.unsplash.com/photo-1585032226651-759b368d7246?w=500&q=80'},
            {'name': '얼큰 해물 짬뽕', 'price': 8500, 'image': 'https://images.unsplash.com/photo-1512058560366-cd2429555614?w=500&q=80'},
            {'name': '새우 볶음밥', 'price': 8000, 'image': 'https://images.unsplash.com/photo-1603133872878-684f208fb84b?w=500&q=80'}
        ],
        '🥟 요리류': [
            {'name': '바삭 탕수육 (등심)', 'price': 18000, 'image': 'https://images.unsplash.com/photo-1525755662778-989d0524087e?w=500&q=80'},
            {'name': '매콤 칠리새우', 'price': 25000, 'image': 'https://images.unsplash.com/photo-1551504734-5ee1c4a1479b?w=500&q=80'}
        ]
    },
    '분식/매점': {
        '🍳 분식 대표': [
            {'name': '매콤 떡볶이', 'price': 5000, 'image': 'https://images.unsplash.com/photo-1534353436294-0dbd4bdac845?w=500&q=80'},
            {'name': '모둠 튀김', 'price': 6000, 'image': 'https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=500&q=80'},
            {'name': '찰순대', 'price': 4500, 'image': 'https://images.unsplash.com/photo-1598515214211-89d3c73ae83b?w=500&q=80'}
        ]
    },
    '치킨/호프': {
        '🍗 메인 메뉴': [
            {'name': '바삭 후라이드', 'price': 18000, 'image': ''},
            {'name': '달콤 양념치킨', 'price': 19000, 'image': ''}
        ]
    },
    '꽃집/플라워': {
        '💐 꽃다발/선물': [
            {'name': '프리지아 한발 (계절)', 'price': 15000, 'image': ''},
            {'name': '로맨틱 장미 다발', 'price': 35000, 'image': ''},
            {'name': '감사 카네이션', 'price': 12000, 'image': ''}
        ],
        '🪴 식물/화분': [
            {'name': '공기정화 스투키', 'price': 25000, 'image': ''},
            {'name': '행운의 개운죽', 'price': 8000, 'image': ''}
        ]
    }
}

def get_ai_recommended_menu(business_type):
    """업종 키워드를 분석하여 가장 적절한 AI 메뉴 프리셋을 반환하며, 모든 메뉴 항목에 고유 ID를 부여합니다."""
    if not business_type: 
        return {"🔍 추천 메뉴": [{"id": 1, "name": "매장 명칭을 기반으로 메뉴를 추가해 주세요", "price": 0, "image": ""}]}
    
    # 키워드 매칭 정교화 (대소문자 무시)
    biz_type = business_type.lower()
    menu_template = {"✨ 추천 메뉴": []}
    
    if any(k in biz_type for k in ['커피', '카페', '찻집', '다방', '디저트', '음료']):
        menu_template = AI_MENU_PRESETS.get('커피/카페')
    elif any(k in biz_type for k in ['중식', '중국집', '짜장', '짬뽕', '마라탕']):
        menu_template = AI_MENU_PRESETS.get('중식/차이니즈')
    elif any(k in biz_type for k in ['한식', '식당', '밥집', '국밥', '찌개', '갈비', '고기']):
        menu_template = AI_MENU_PRESETS.get('한식/식당')
    elif any(k in biz_type for k in ['분식', '떡볶이', '김밥', '매점', '포장마차']):
        menu_template = AI_MENU_PRESETS.get('분식/매점')
    elif any(k in biz_type for k in ['치킨', '호프', '닭', '통닭', '맥주']):
        menu_template = AI_MENU_PRESETS.get('치킨/호프')
    elif any(k in biz_type for k in ['꽃', '플라워', '화분', '원예', '식물']):
        menu_template = AI_MENU_PRESETS.get('꽃집/플라워')
    else:
        menu_template = {"🔍 추천 메뉴": [{"name": "이곳에 첫 메뉴를 추가해 보세요!", "price": 0, "image": ""}]}

    # 모든 메뉴 항목에 순차적인 ID 부여 (Socket.IO 주문 처리 시 필수)
    item_id = 1
    for category in menu_template:
        for item in menu_template[category]:
            item['id'] = item_id
            item_id += 1
            
    return menu_template

def get_ai_operation_insight(store):
    """매장의 현재 데이터를 분석하여 AI 운영 인사이트를 생성합니다."""
    insights = [
        "🌞 오늘은 날씨가 맑습니다! 테라스석이나 창가 자리 주문이 많아질 수 있어요.",
        "📊 최근 1시간 포인트 적립률이 높습니다. 단골 고객이 많이 오셨네요! 친절한 인사가 매출을 올립니다.",
        "👥 오늘 지각한 직원이 한 명도 없습니다. 팀워크 최상! 점심 회식이라도 어떨까요?",
        "💡 주말 전 금요일입니다. 세트 메뉴 주문이 몰릴 수 있으니 재료를 미리 준비하세요.",
        "✨ '아메리카노' 클릭률이 급상승 중입니다. 메인 화면 배너로 올려보길 추천합니다.",
        "📉 화요일은 상대적으로 한가합니다. '화요 타임 어택' 이벤트를 구상해 보세요!"
    ]
    return random.choice(insights)
