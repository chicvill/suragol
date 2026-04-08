import random

# ---------------------------------------------------------
# AI 메뉴 추천 프리셋 (업종별 자동 생성용)
# ---------------------------------------------------------
AI_MENU_PRESETS = {
    '커피/카페': {
        '☕ 에스프레소/커피': [
            {'name': '아메리카노 (HOT/ICE)', 'price': 4500, 'image': '/static/images/sample_coffee.jpg'},
            {'name': '카페라떼', 'price': 5000, 'image': ''},
            {'name': '바닐라라떼', 'price': 5500, 'image': ''}
        ],
        '🍰 디저트': [
            {'name': '전통 다과 세트', 'price': 7500, 'image': ''},
            {'name': '치즈 케이크', 'price': 6500, 'image': ''}
        ]
    },
    '한식/식당': {
        '🥘 식사류': [
            {'name': '전통 비빔밥', 'price': 9000, 'image': ''},
            {'name': '김치찌개 정식', 'price': 8500, 'image': ''},
            {'name': '뚝배기 불고기', 'price': 11000, 'image': ''}
        ]
    },
    '분식/매점': {
        '🍳 분식 대표': [
            {'name': '매콤 떡볶이', 'price': 5000, 'image': ''},
            {'name': '모둠 튀김', 'price': 6000, 'image': ''},
            {'name': '찰순대', 'price': 4500, 'image': ''}
        ]
    },
    '치킨/호프': {
        '🍗 메인 메뉴': [
            {'name': '바삭 후라이드', 'price': 18000, 'image': ''},
            {'name': '달콤 양념치킨', 'price': 19000, 'image': ''}
        ]
    }
}

def get_ai_recommended_menu(business_type):
    """업종 키워드를 분석하여 가장 적절한 AI 메뉴 프리셋을 반환합니다."""
    if not business_type: 
        return {"🔍 추천 메뉴": [{"name": "매장 명칭을 기반으로 메뉴를 추가해 주세요", "price": 0, "image": ""}]}
    
    # 키워드 매칭 정교화 (대소문자 무시)
    biz_type = business_type.lower()
    if any(k in biz_type for k in ['커피', '카페', '찻집', '다방', '디저트', '음료']):
        return AI_MENU_PRESETS.get('커피/카페', {"✨ 추천 메뉴": []})
    if any(k in biz_type for k in ['한식', '식당', '밥집', '국밥', '찌개', '갈비', '고기']):
        return AI_MENU_PRESETS.get('한식/식당', {"✨ 추천 메뉴": []})
    if any(k in biz_type for k in ['분식', '떡볶이', '김밥', '매점', '포장마차']):
        return AI_MENU_PRESETS.get('분식/매점', {"✨ 추천 메뉴": []})
    if any(k in biz_type for k in ['치킨', '호프', '닭', '통닭', '맥주']):
        return AI_MENU_PRESETS.get('치킨/호프', {"✨ 추천 메뉴": []})
        
    return {"🔍 추천 메뉴": [{"name": "이곳에 첫 메뉴를 추가해 보세요!", "price": 0, "image": ""}]}

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
