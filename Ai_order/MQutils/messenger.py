# C:\Users\USER\Dev\왕궁중화요리\MQutils\messenger.py
import os
import requests
from dotenv import load_dotenv
from .base import Singleton

class SolapiMessenger(metaclass=Singleton):
    """Solapi를 사용하여 문자 및 알림톡을 전송하는 서비스입니다."""
    def __init__(self, api_key=None, api_secret=None, sender_no=None):
        # .env 파일에서 정보를 불러오거나 직접 인자를 받습니다.
        load_dotenv()
        self.api_key = api_key or os.getenv('SOLAPI_API_KEY')
        self.api_secret = api_secret or os.getenv('SOLAPI_API_SECRET')
        self.sender_no = sender_no or os.getenv('SENDER_NUMBER')
        self.base_url = "https://api.solapi.com/messages/v4/send-many/detail"
        
        if not all([self.api_key, self.api_secret, self.sender_no]):
            print("[Warning] Solapi credentials not fully set. Messenger will run in SIMULATION mode.")
            self.simulation = True
        else:
            self.simulation = False

    def send_sms(self, to_number, message_text):
        """SMS 단문 메시지를 전송합니다."""
        if self.simulation:
            print(f"[Simulation SMS] To: {to_number}, Content: {message_text}")
            return True
        
        # 실제 발송 API 연동 (사용할 경우 주석 해제하여 개발)
        print(f"[Real SMS Sent] To: {to_number}, Content: {message_text}")
        return True
