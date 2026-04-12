import random
from datetime import datetime, timedelta
from app import app, db
from models import Store, Order, OrderItem, Customer, PointTransaction

def seed_demo_data():
    with app.app_context():
        store_id = 'wangpung'
        store = Store.query.get(store_id)
        
        if not store:
            print(f"Store {store_id} not found. Creating it first...")
            menu_data = {
                "면류 (Noodles)": [
                    {"name": "왕궁 짜장면", "price": 7000, "image": ""},
                    {"name": "해물 짬뽕", "price": 9000, "image": ""},
                    {"name": "쟁반 짜장 (2인)", "price": 16000, "image": ""}
                ],
                "요리류 (Main Dish)": [
                    {"name": "찹쌀 탕수육 (소)", "price": 18000, "image": ""},
                    {"name": "찹쌀 탕수육 (대)", "price": 28000, "image": ""},
                    {"name": "깐풍기", "price": 25000, "image": ""},
                    {"name": "양장피", "price": 30000, "image": ""}
                ],
                "식사류 (Rice)": [
                    {"name": "볶음밥", "price": 8000, "image": ""},
                    {"name": "짬뽕밥", "price": 9000, "image": ""},
                    {"name": "잡채밥", "price": 10000, "image": ""}
                ]
            }
            store = Store(
                id=store_id,
                name='왕궁중화요리',
                tables_count=12,
                menu_data=menu_data,
                status='active',
                payment_status='paid'
            )
            db.session.add(store)
            db.session.commit()

        # [1] Create Dummy Customers
        print("Creating dummy customers...")
        phones = [f"010-1234-567{i}" for i in range(10)]
        customers = []
        for phone in phones:
            cust = Customer.query.filter_by(store_id=store_id, phone=phone).first()
            if not cust:
                cust = Customer(store_id=store_id, phone=phone, points=0, visit_count=0, total_spent=0)
                db.session.add(cust)
            customers.append(cust)
        db.session.commit()

        # [2] Create Dummy Orders for the last 30 days
        print("Creating dummy orders...")
        menus = []
        for cat, items in store.menu_data.items():
            for item in items:
                menus.append(item)

        now = datetime.utcnow()
        for i in range(100):
            # Random date in last 30 days
            days_ago = random.randint(0, 30)
            order_time = now - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))
            
            table_id = random.randint(1, store.tables_count)
            order_id = f"demo_{order_time.strftime('%Y%m%d%H%M%S')}_{i}"
            
            cust = random.choice(customers)
            
            order = Order(
                id=order_id,
                store_id=store_id,
                table_id=table_id,
                status='paid',
                created_at=order_time,
                paid_at=order_time + timedelta(minutes=random.randint(20, 60)),
                phone=cust.phone
            )
            
            total_price = 0
            # 1-4 random items
            num_items = random.randint(1, 4)
            for _ in range(num_items):
                m = random.choice(menus)
                qty = random.randint(1, 2)
                item_price = m['price'] * qty
                total_price += item_price
                
                order_item = OrderItem(
                    order_id=order_id,
                    menu_id=0, # Dummy menu id
                    name=m['name'],
                    price=m['price'],
                    quantity=qty,
                    status='pending'
                )
                db.session.add(order_item)
            
            order.total_price = total_price
            db.session.add(order)
            
            # Update customer stats
            cust.visit_count += 1
            cust.total_spent += total_price
            cust.points += int(total_price * 0.05) # 5% accumulation
        
        db.session.commit()
        print(f"Successfully seeded 100 orders for store '{store_id}'.")

if __name__ == "__main__":
    seed_demo_data()
