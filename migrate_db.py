from app import app
from models import db
from sqlalchemy import text

def migrate():
    with app.app_context():
        print("Starting Database Migration...")
        
        # 1. Add 'phone' to 'orders' table
        try:
            db.session.execute(text("ALTER TABLE orders ADD COLUMN phone VARCHAR(20)"))
            db.session.commit()
            print("✅ Added 'phone' column to 'orders' table.")
        except Exception as e:
            db.session.rollback()
            print(f"ℹ️ 'orders.phone' notice: {e}")

        # 2. Add 'visit_count' and 'total_spent' to 'customers' table 
        # (In case it was created in a previous step without these columns)
        try:
            db.session.execute(text("ALTER TABLE customers ADD COLUMN visit_count INTEGER DEFAULT 0"))
            db.session.execute(text("ALTER TABLE customers ADD COLUMN total_spent INTEGER DEFAULT 0"))
            db.session.commit()
            print("✅ Added 'visit_count' and 'total_spent' to 'customers' table.")
        except Exception as e:
            db.session.rollback()
            print(f"ℹ️ 'customers' columns notice: {e}")

        # 3. Ensure new tables are created (ServiceRequest, Customer, PointTransaction)
        try:
            db.create_all()
            print("✅ Checked/Created all new tables.")
        except Exception as e:
            print(f"❌ Error during create_all: {e}")

if __name__ == "__main__":
    migrate()
