# -*- coding: utf-8 -*-
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.String(50), primary_key=True)
    table_id = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='pending')  # pending, ready, served, paid
    session_id = db.Column(db.String(50), nullable=True)   # 고객 식별 세션 ID
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)
    
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'table_id': self.table_id,
            'total_price': self.total_price,
            'status': self.status,
            'session_id': self.session_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'items': [item.to_dict() for item in self.items]
        }

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(50), db.ForeignKey('orders.id'), nullable=False)
    menu_id = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, default=1)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'price': self.price,
            'quantity': self.quantity
        }
class Waiting(db.Model):
    __tablename__ = 'waiting'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    waiting_no = db.Column(db.Integer, nullable=True) # 3자리 난수 대기 번호
    phone = db.Column(db.String(20), nullable=False)
    people = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default='waiting') # waiting, entered, cancelled
    notified = db.Column(db.Boolean, default=False) # Rank 3 notice sent?
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'waiting_no': self.waiting_no,
            'phone': self.phone,
            'people': self.people,
            'status': self.status,
            'notified': self.notified,
            'created_at': self.created_at.isoformat()
        }
