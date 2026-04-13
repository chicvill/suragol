import os
import pg8000.dbapi
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# [강제 보정] 6543 포트 및 주소Lookup 에러 방지
if DATABASE_URL:
    if ":6543" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace(":6543", ":5432")
    if "aws-1-ap-south-1.pooler.supabase.com" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("aws-1-ap-south-1.pooler.supabase.com", "wdikgmyhuxhhyeljnyqa.pooler.supabase.com")
    if "wdikgmyhuxhhyeljnyqa.pooler.supabase.com" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("wdikgmyhuxhhyeljnyqa.pooler.supabase.com", "db.wdikgmyhuxhhyeljnyqa.supabase.co")

def update_order_payment_status(sender_name, amount, order_no=""):
    """
    입금자명 또는 주문번호와 금액을 기준으로 매칭되는 주문을 찾아 결제 완료 처리함
    """
    if amount <= 0:
        return {"status": "error", "message": "Invalid amount"}

    conn = None
    try:
        # DB 연결 (SSL 강제 활성화)
        import ssl
        ssl_context = ssl.create_default_context()
        conn = pg8000.dbapi.connect(dsn=DATABASE_URL, ssl_context=ssl_context)
        cur = conn.cursor()
        
        # 1. 매칭되는 주문 찾기 
        # 주문번호(order_no)가 있으면 최우선으로 검색, 없으면 입금자명으로 검색
        if order_no:
            query = """
                SELECT id, store_id, table_id, total_price 
                FROM orders 
                WHERE order_no = %s AND total_price = %s AND status != 'paid'
                ORDER BY created_at DESC LIMIT 1
            """
            cur.execute(query, (order_no, amount))
        else:
            query = """
                SELECT id, store_id, table_id, total_price 
                FROM orders 
                WHERE depositor_name = %s AND total_price = %s AND status != 'paid'
                ORDER BY created_at DESC LIMIT 1
            """
            cur.execute(query, (sender_name, amount))
            
        order = cur.fetchone()
        
        # 3. 알림 기록 추가 (매칭 여부와 상관없이 기록하여 카운터에 플로팅으로 띄움)
        status_to_save = 'matched' if order else 'unconfirmed'
        insert_notification_query = """
            INSERT INTO bank_notifications (store_id, sender, amount, order_no, raw_content, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        store_id = order[1] if order else None
        cur.execute(insert_notification_query, (store_id, sender_name, amount, order_no, "", status_to_save, datetime.utcnow()))
        conn.commit()
        
        if not order:
            return {"status": "not_found", "message": f"Matching order for {sender_name} ({amount}원) not found."}
            
        order_id = order[0]
        
        # 2. 주문 상태 업데이트
        update_query = """
            UPDATE orders 
            SET status = 'paid', paid_at = %s 
            WHERE id = %s
        """
        cur.execute(update_query, (datetime.utcnow(), order_id))
        conn.commit()
        
        print(f"[DB Success] Order {order_id} updated to 'paid' for {sender_name}")
        return {
            "status": "success", 
            "order_id": order_id, 
            "store_id": order[1], 
            "table_id": order[2],
            "sender": sender_name,
            "amount": amount
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[DB Error] {e}")
        return {"status": "error", "message": str(e)}
    finally:
        if conn:
            cur.close()
            conn.close()

if __name__ == "__main__":
    # 테스트용
    print(update_order_payment_status("테스트", 1000))
