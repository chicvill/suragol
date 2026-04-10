import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def migrate():
    print(f"[Migration] Connecting to DB...")
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        print(f"[Migration] Adding 'depositor_name' column to 'orders' table...")
        cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS depositor_name VARCHAR(100);")
        
        print(f"[Migration] Adding bank info columns to 'stores' table...")
        cur.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS bank_name VARCHAR(50);")
        cur.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS account_no VARCHAR(50);")
        cur.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS account_holder VARCHAR(50);")
        
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
