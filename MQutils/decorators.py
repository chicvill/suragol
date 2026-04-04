from functools import wraps
from flask import session, redirect, url_for, flash

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @login_required
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash("관리자 권한이 필요합니다.")
            return redirect(url_for('admin_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def staff_required(f):
    @login_required
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') not in ['admin', 'staff']:
            flash("직원 이상의 권한이 필요합니다.")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def store_access_required(f):
    @login_required
    @wraps(f)
    def decorated_function(slug, *args, **kwargs):
        if session.get('role') in ['admin', 'staff']:
            return f(slug, *args, **kwargs)
        if session.get('store_id') != slug:
            return "접근 권한이 없습니다.", 403
        return f(slug, *args, **kwargs)
    return decorated_function
