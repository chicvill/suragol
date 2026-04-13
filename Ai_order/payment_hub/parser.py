import re

class BankParser:
    """
    은행별 입금 문자/알림 패턴을 분석하는 파서 클래스
    """
    
    @staticmethod
    def parse_korea_bank_format(text):
        """
        다양한 한국 입금 알림 패턴 분석
        패턴 1 (KB): [KB]04/10 15,000원 입금(홍길동)
        패턴 2 (스크린샷): 민흥식 2022... / mqnet 1000원
        """
        # 1. 금액 추출 (숫자와 쉼표 + '원')
        # "입금250,000원" 또는 "250,000원" 모두 대응
        amount_match = re.search(r'(?:입금)?([\d,]+)\s*원', text)
        amount = 0
        if amount_match:
            amount = int(amount_match.group(1).replace(',', ''))
            
        # 2. 입금자명 추출 
        sender = ""
        
        # 실제 은행 데이터와 전송 앱의 메타데이터 분리 시도
        # "농협", "입금", "원" 등 은행 키워드가 시작되는 지점 이후를 실제 본문으로 간주
        bank_data_match = re.search(r'(농협|입금|[\d,]+원).*', text, re.DOTALL)
        content_to_parse = bank_data_match.group(0) if bank_data_match else text
        
        # 패턴 A: 농협 스타일 (003-배종봉) - 실제 본문에서 찾기
        nh_style_match = re.search(r'(?:[\d]{3}-)?([가-힣]{2,4})', content_to_parse)
        if nh_style_match and nh_style_match.group(1) not in ['농협', '입금']:
            sender = nh_style_match.group(1)

        # 패턴 B: 본문 하단의 "잔액" 바로 앞 단어 (매우 정확한 위치)
        if not sender:
            balance_match = re.search(r'(\S+)\s+잔액', content_to_parse)
            if balance_match:
                # 003-배종봉 에서 배종봉만 추출
                sender = balance_match.group(1).split('-')[-1]
        
        # 패턴 C: 괄호 안 이름 (메타데이터 제외하고 본문에서만 찾기)
        if not sender:
            paren_match = re.search(r'\(([^)]+)\)', content_to_parse)
            if paren_match:
                sender = paren_match.group(1).split()[0]
            
        # 마지막 수단: 원형 텍스트에서 괄호 찾기 (하위 호환성)
        if not sender:
            fallback_match = re.search(r'입금\((.*?)\)', text)
            if fallback_match:
                sender = fallback_match.group(1).strip()
            
        # 3. 주문번호(4자리 숫자) 추출 시도
        order_no = ""
        # 4자리 숫자가 독립적으로 있거나 이름 뒤에 붙어 있는 경우 탐색
        order_no_match = re.search(r'(?<!\d)(\d{4})(?!\d)', text)
        if order_no_match:
            order_no = order_no_match.group(1)
            
        return {
            "amount": amount,
            "sender": sender,
            "order_no": order_no,
            "raw": text.replace('\n', ' ')
        }

# 테스트 코드
if __name__ == "__main__":
    test_msg = "[KB]04/10 06:45 15,000원 입금(홍길동) 잔액 100,200원"
    result = BankParser.parse_korea_bank_format(test_msg)
    print(f"Parsed Result: {result}")
