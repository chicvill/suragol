from flask import request, session, render_template, redirect, url_for, flash
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from models import db, User

def init_auth_routes(app):
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            try:
                username = request.form.get('username', '').strip()
                password = request.form.get('password', '').strip()
                
                if not username or not password:
                    flash("아이디와 비밀번호를 모두 입력해 주세요.")
                    return redirect(url_for('login'))

                user = User.query.filter_by(username=username).first()
                if user and check_password_hash(user.password, password):
                    # Staff 권한은 관리자 승인이 필요함
                    if user.role == 'staff' and not user.is_approved:
                        flash("아직 관리자의 승인이 대기 중입니다. 승인 후 이용 가능합니다.")
                        return redirect(url_for('login'))
                    
                    session.permanent = True
                    session.update({'user_id': user.id, 'username': user.username, 'role': user.role, 'store_id': user.store_id})
                    
                    # next 파라미터가 있으면 원래 페이지로 복귀, 없으면 대시보드로
                    next_url = request.args.get('next') or request.form.get('next')
                    if next_url and next_url.startswith('/'):
                        return redirect(next_url)
                    return redirect(url_for('index'))
                
                else:
                    flash("⚠️ 아이디 또는 비밀번호를 확인해주세요.")
            except Exception as e:
                import traceback
                print(f"❌ [로그인 오류 상세]")
                traceback.print_exc()
                print(f"----------------------")
                flash("시스템 처리 중 오류가 발생했습니다.")
                
        return render_template('index.html', logged_in=False)

    @app.route('/signup', methods=['GET', 'POST'])
    def signup():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            full_name = request.form.get('full_name')
            phone = request.form.get('phone')
            # 역할 선택 (admin은 자가 가입 불가)
            selected_role = request.form.get('role', 'staff')
            if selected_role == 'admin': selected_role = 'staff'
            
            store_id = request.form.get('store_id', '').strip()
            
            # 유효성 검사: 점장(manager), 근로자(worker)는 업소 코드가 필수
            if selected_role in ['manager', 'worker'] and not store_id:
                flash("해당 등급으로 가입하려면 소속 업소 코드가 필요합니다.")
                return redirect(url_for('signup', role=selected_role))

            # 약관 동의 체크
            agree_profit = 'agree_profit' in request.form
            agree_privacy = 'agree_privacy' in request.form
            agree_age = 'agree_age' in request.form
            agree_not_robot = 'agree_not_robot' in request.form
            agree_labor = 'agree_labor' in request.form if selected_role == 'worker' else True

            if not all([agree_profit, agree_privacy, agree_age, agree_not_robot, agree_labor]):
                flash("모든 필수 약관에 동의하셔야 가입 신청이 가능합니다.")
                return redirect(url_for('signup', role=selected_role, store_id=store_id))

            if password != confirm_password:
                flash("비밀번호가 일치하지 않습니다.")
                return redirect(url_for('signup', role=selected_role, store_id=store_id))

            if User.query.filter_by(username=username).first():
                flash("이미 사용 중인 아이디입니다.")
                return redirect(url_for('signup', role=selected_role, store_id=store_id))

            # 근로자 전용 스케줄 및 계약 데이터 처리
            contract_start = request.form.get('contract_start')
            contract_end = request.form.get('contract_end')
            
            work_schedule = {}
            for d in ['mon','tue','wed','thu','fri','sat','sun']:
                tin = request.form.get(f'sched_{d}_in')
                tout = request.form.get(f'sched_{d}_out')
                if tin and tout:
                    work_schedule[d] = {'in': tin, 'out': tout}

            role_labels = {'owner': '점주', 'manager': '점장', 'worker': '현장 근로자', 'staff': '파트너'}
            new_user = User(
                username=username,
                password=generate_password_hash(password),
                role=selected_role,
                full_name=full_name,
                phone=phone,
                store_id=store_id if store_id else None,
                is_approved=False,  # 이제 점주가 검토 후 승인
                agreed_at=datetime.utcnow(),
                contract_start=datetime.strptime(contract_start, '%Y-%m-%d').date() if contract_start else None,
                contract_end=datetime.strptime(contract_end, '%Y-%m-%d').date() if contract_end else None,
                work_schedule=work_schedule if work_schedule else None
            )
            db.session.add(new_user)
            db.session.commit()
            flash(f"✅ {role_labels.get(selected_role, '')} 가입 신청이 완료되었습니다. 관리자 승인 후 이용 가능합니다.")
            return redirect(url_for('login'))

        return render_template('signup.html')

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))
