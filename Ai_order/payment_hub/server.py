import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

app = Flask(__name__)

# 보안을 위한 API 토큰 (모바일 앱과 일치해야 함)
PAYMENT_SECRET_TOKEN = os.getenv("PAYMENT_SECRET_TOKEN", "your_secret_token_here")

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "message": "Payment Hub is running"}), 200

@app.route('/webhook/payment', methods=['GET', 'POST'])
def receive_payment_notification():
    # 1. 인증 확인
    token = request.headers.get('X-Payment-Token')
    if token != PAYMENT_SECRET_TOKEN:
        print(f"[Auth Error] Invalid Token: {token}")
        return jsonify({"error": "Unauthorized"}), 401

    # 2. 데이터 추출 (GET 또는 POST)
    msg_content = ""
    if request.method == 'POST':
        data = request.get_json(silent=True)
        if data:
            # 여러 가지 키 이름 지원 (msg, key, content)
            msg_content = data.get('msg') or data.get('key') or data.get('content')
            if not msg_content:
                msg_content = str(data)
        else:
            # Form 데이터인 경우 처리
            msg_content = request.form.get('msg') or request.form.get('key') or request.form.get('content')
    else:
        # GET 요청에서 'msg' 또는 'key' 쿼리 파라미터 확인
        msg_content = request.args.get('msg') or request.args.get('key', '')

    if not msg_content:
        print("[Warning] No message content received")
        return jsonify({"error": "No message content"}), 400

    print(f"[Payment Notification Received] Content: {msg_content}")

    # 3. 파싱 (parser.py 활용)
    try:
        from parser import BankParser
        from database import update_order_payment_status
        
        parsed_data = BankParser.parse_korea_bank_format(msg_content)
        print(f"[Parsed Data] {parsed_data}")
        
        # 4. DB 업데이트 시도 (이름, 금액, 주문번호 사용)
        db_result = update_order_payment_status(
            parsed_data['sender'], 
            parsed_data['amount'], 
            parsed_data['order_no']
        )
        print(f"[DB Response] {db_result}")
        
        return jsonify({
            "status": "success",
            "parsed": parsed_data,
            "db_result": db_result
        }), 200
    except Exception as e:
        print(f"[Error] Processing failed: {e}")
        return jsonify({"error": "Processing error", "details": str(e)}), 500

if __name__ == '__main__':
    # 테스트를 위해 10001 포트에서 실행
    app.run(host='0.0.0.0', port=10001, debug=True)
