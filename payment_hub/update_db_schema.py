import pg8000.dbapi
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    if ":6543" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace(":6543", ":5432")
    if "aws-1-ap-south-1.pooler.supabase.com" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("aws-1-ap-south-1.pooler.supabase.com", "wdikgmyhuxhhyeljnyqa.pooler.supabase.com")
    if "wdikgmyhuxhhyeljnyqa.pooler.supabase.com" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("wdikgmyhuxhhyeljnyqa.pooler.supabase.com", "db.wdikgmyhuxhhyeljnyqa.supabase.co")

def migrate():
    print(f"[Migration] Connecting to DB...")
    conn = None
    try:
        from sqlalchemy.engine import make_url
        url = make_url(DATABASE_URL)
        
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        print(f"[Migration] Connecting to {url.host}:{url.port}...")
        conn = pg8000.dbapi.connect(
            host=url.host,
            port=url.port,
            user=url.username,
            password=url.password,
            database=url.database,
            ssl_context=ssl_context
        )
        cur = conn.cursor()
        
        print(f"[Migration] Adding 'depositor_name' column to 'orders' table...")
        cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS depositor_name VARCHAR(100);")
        
        print(f"[Migration] Adding bank info columns to 'stores' table...")
        cur.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS bank_name VARCHAR(50);")
        cur.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS account_no VARCHAR(50);")
        cur.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS account_holder VARCHAR(50);")
        
        print(f"[Migration] Adding 'payment_method' column to 'orders' table...")
        cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20);")
        
        conn.commit()
        print("[Migration] Success! Database schema updated.")
    except Exception as e:
        print(f"[Migration Error] {e}")
    finally:
        if conn:
            cur.close()
            conn.close()

if __name__ == "__main__":
    migrate()
