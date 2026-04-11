import os
import json
from app import app
from models import db, Store

with app.app_context():
    stores = db.session.query(Store).all()
    results = []
    for s in stores:
        results.append({
            'id': s.id,
            'name': s.name,
            'bank_name': s.bank_name,
            'account_no': s.account_no
        })
    with open('scratch_db_output.txt', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
