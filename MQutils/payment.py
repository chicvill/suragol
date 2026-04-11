import os
import uuid
from datetime import datetime
from .base import Singleton

class MQPaymentManager(metaclass=Singleton):
    """
    [MQnet 통합 결제 매니저]
    모든 결제(매장 주문, 본사 수수료, 파트너 정산)를 이 모듈을 통해 처리합니다.
    """
    
    def __init__(self):
        # MQnet 본사 공식 수취 계좌 정보 (환경변수 또는 기본값)
        self.hq_bank = os.environ.get('HQ_BANK_NAME', '농협은행')
        self.hq_account = os.environ.get('HQ_ACCOUNT_NO', '302-0000-0000-00')
        self.hq_holder = os.environ.get('HQ_ACCOUNT_HOLDER', '(주)MQ네트웍스')

    def create_payment_request(self, category, amount, target_id, method='TRANSFER'):
        """
        결제 요청 생성
        :param category: 'ORDER'(매장주문), 'SAAS_FEE'(이용료), 'AD_FEE'(광고비)
        :param amount: 금액
        :param target_id: 주문ID 또는 매장ID
        :param method: 'TRANSFER'(이체), 'CARD'(카드), 'POINT'(포인트)
        """
        transaction_id = f"TX-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        
        if method == 'TRANSFER':
            return self._handle_transfer(category, amount, transaction_id)
        elif method == 'CARD':
            return self._handle_card_payment(category, amount, transaction_id)
        
        return {"status": "error", "message": "지원하지 않는 결제 수단입니다."}

    def _handle_transfer(self, category, amount, tx_id):
        """무통장 입금/이체 정보 생성"""
        # 본사 이용료 납부일 경우 본사 계좌, 매장 주문일 경우 해당 매장 계좌 정보를 반환
        return {
            "status": "pending",
            "method": "TRANSFER",
            "transaction_id": tx_id,
            "category": category,
            "display_msg": "계좌로 입금해 주세요.",
            "bank_info": {
                "bank": self.hq_bank if category != 'ORDER' else "해당 매장 지정 계좌",
                "account": self.hq_account if category != 'ORDER' else "해당 매장 계좌번호",
                "holder": self.hq_holder if category != 'ORDER' else "해당 매장 예금주",
                "amount": amount
            }
        }

    def _handle_card_payment(self, category, amount, tx_id):
        """카드/간편결제 - Toss Payments 등 연동 포인트"""
        # 향후 여기에 Toss SDK 연동 로직 삽입
        return {
            "status": "ready",
            "method": "CARD",
            "transaction_id": tx_id,
            "checkout_url": f"/payment/checkout/{tx_id}?amount={amount}&cat={category}"
        }

    def verify_transaction(self, tx_id):
        """결제 완료 검증 로직 (입금 확인/PG사 승인 확인)"""
        # TODO: Payment Hub나 PG사 API를 통해 실제 입금/승인 여부를 체크
        return True

class MQReceiptManager:
    """영수증 및 증빙 서류 발행 모듈"""
    
    @staticmethod
    def generate_digital_receipt(tx_data):
        """디지털 영수증 데이터 구성"""
        return {
            "title": "MQnet 서비스 이용 영수증" if tx_data['category'] != 'ORDER' else "주문 영수증",
            "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "tx_id": tx_data['transaction_id'],
            "amount": tx_data['amount'],
            "status": "결제완료"
        }
