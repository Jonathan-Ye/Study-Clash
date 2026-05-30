from datetime import datetime, date, timedelta, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, DailyStats, LoginAttempt
from app.utils.security import validate_password, get_password_policy_config, rate_limit

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
@rate_limit(3, 60, key_func=lambda: f"register:{request.remote_addr}")
def register():
    from app.models import SystemSetting
    registration_enabled = SystemSetting.get('registration_enabled', 'true') == 'true'
    
    if not registration_enabled:
        flash('系统暂未开放注册功能', 'error')
        return redirect(url_for('auth.login'))
    
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        nickname = request.form.get('nickname')
        grade = request.form.get('grade')
        school = request.form.get('school')
        
        if not username or not email or not password:
            flash('请填写所有必填字段', 'error')
            return redirect(url_for('auth.register'))
        
        if password != confirm_password:
            flash('两次输入的密码不一致', 'error')
            return redirect(url_for('auth.register'))
        
        # 密码策略校验
        is_valid, errors = validate_password(password)
        if not is_valid:
            for err in errors:
                flash(err, 'error')
            return redirect(url_for('auth.register'))
        
        if User.query.filter_by(username=username).first():
            flash('用户名已被使用', 'error')
            return redirect(url_for('auth.register'))
        
        if User.query.filter_by(email=email).first():
            flash('邮箱已被注册', 'error')
            return redirect(url_for('auth.register'))
        
        user = User()
        user.username = username
        user.email = email
        user.set_password(password)
        user.nickname = nickname or username
        user.grade = grade
        user.school = school
        user.role = 'student'
        
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        
        stats = DailyStats.get_or_create(user.id)
        stats.login = True
        db.session.commit()
        
        flash('注册成功！欢迎加入学习对战', 'success')
        return redirect(url_for('main.index'))
    
    return render_template('auth/register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
@rate_limit(5, 60, key_func=lambda: f"login:{request.form.get('username', request.remote_addr)}")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember') == 'on'
        
        if not username or not password:
            flash('请输入用户名和密码', 'error')
            return redirect(url_for('auth.login'))
        
        # 检查登录锁定（管理员豁免）
        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()
        
        if user and user.role != 'admin':
            is_locked, remaining = LoginAttempt.is_locked(user.username)
            if is_locked:
                flash(f'账户已锁定，请{remaining}分钟后重试', 'error')
                return redirect(url_for('auth.login'))
        
        if not user or not user.check_password(password):
            # 记录登录失败
            if user and user.role != 'admin':
                record = LoginAttempt.record_failure(user.username)
                # 检查是否需要锁定
                try:
                    from app.models.system import SystemSetting
                    max_attempts = int(SystemSetting.get('max_login_attempts', '5'))
                    lockout_duration = int(SystemSetting.get('lockout_duration', '30'))
                except Exception:
                    max_attempts = 5
                    lockout_duration = 30
                
                if record.fail_count >= max_attempts:
                    LoginAttempt.lock_account(username, lockout_duration)
                    flash(f'密码错误次数过多，账户已锁定{lockout_duration}分钟', 'error')
                    # 记录安全日志
                    try:
                        from app.utils.op_log import log_operation
                        log_operation('account_lockout', 'security', target_name=username,
                                    detail=f'fail_count={record.fail_count}, lockout={lockout_duration}min')
                    except Exception:
                        pass
                else:
                    flash('用户名或密码错误', 'error')
            else:
                flash('用户名或密码错误', 'error')
            
            # 记录登录失败安全日志
            try:
                from app.utils.op_log import log_operation
                if user:
                    log_operation('login_fail', 'security', target_name=username,
                                detail=f'user_role={user.role}')
            except Exception:
                pass
            
            return redirect(url_for('auth.login'))
        
        if not user.is_active:
            flash('账户已被禁用', 'error')
            return redirect(url_for('auth.login'))
        
        # 登录成功，重置失败计数
        LoginAttempt.reset(username)
        
        login_user(user, remember=remember)

        from app.utils.system_logger import SystemLogger
        SystemLogger.info(f'用户登录成功 | username={username} | role={user.role}', category='auth',
                         user={'id': user.id, 'username': user.username})
        
        today = date.today()
        # 在更新last_login之前判断是否连续签到
        is_consecutive = user.last_login and user.last_login.date() == today - timedelta(days=1)
        user.last_login = datetime.now(timezone.utc)
        
        # 确保使用干净的 session
        try:
            stats = DailyStats.get_or_create(user.id)
            
            if is_consecutive:
                if user.streak_days is None:
                    user.streak_days = 0
                user.streak_days += 1
            elif stats and not stats.login:
                user.streak_days = 1
            
            if stats:
                stats.login = True
            
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # 如果 stats 更新失败，不影响登录流程
            import logging
            logging.getLogger(__name__).warning(f'更新 DailyStats 失败: {str(e)}')
        
        # 检查是否需要强制修改密码
        if user.must_change_password:
            flash('请立即修改默认密码以确保账户安全', 'warning')
            return redirect(url_for('auth.change_password'))
        
        next_page = request.args.get('next')
        # 验证 next 参数：只允许本站相对路径，防止重定向到不存在的外部 URL
        if next_page and (not next_page.startswith('/') or '://' in next_page):
            next_page = None
        # 验证 next 路径是否匹配已有路由，避免重定向到 404 页面
        if next_page:
            try:
                adapter = current_app.url_map.bind('')
                path = next_page.split('?')[0]
                try:
                    adapter.match(path)
                except Exception:
                    adapter.match(path, method='POST')
            except Exception:
                next_page = None
        flash(f'欢迎回来，{user.nickname or user.username}！', 'success')
        return redirect(next_page or url_for('main.index'))
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    from app.utils.system_logger import SystemLogger
    SystemLogger.info('用户登出', category='auth',
                     user={'id': current_user.id, 'username': current_user.username})
    logout_user()
    flash('您已退出登录', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.nickname = request.form.get('nickname') or current_user.username
        current_user.grade = request.form.get('grade')
        current_user.school = request.form.get('school')
        current_user.participate_in_games = request.form.get('participate_in_games') == 'on'
        current_user.show_in_leaderboard = request.form.get('show_in_leaderboard') == 'on'
        
        new_password = request.form.get('new_password')
        if new_password:
            confirm_password = request.form.get('confirm_password')
            if new_password != confirm_password:
                flash('两次输入的密码不一致', 'error')
                return redirect(url_for('auth.profile'))
            # 密码策略校验
            is_valid, errors = validate_password(new_password)
            if not is_valid:
                for err in errors:
                    flash(err, 'error')
                return redirect(url_for('auth.profile'))
            current_user.set_password(new_password)
        
        db.session.commit()
        flash('个人信息更新成功', 'success')
        return redirect(url_for('auth.profile'))
    
    return render_template('auth/profile.html')

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    # GET 请求：显示修改密码表单
    if request.method == 'GET':
        return render_template('auth/change_password.html')
    
    # POST 请求：处理密码修改
    old_password = request.form.get('old_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not current_user.check_password(old_password):
        flash('原密码错误', 'error')
        return redirect(url_for('auth.profile'))
    
    if new_password != confirm_password:
        flash('两次输入的新密码不一致', 'error')
        return redirect(url_for('auth.profile'))
    
    # 密码策略校验
    is_valid, errors = validate_password(new_password)
    if not is_valid:
        for err in errors:
            flash(err, 'error')
        return redirect(url_for('auth.profile'))
    
    current_user.set_password(new_password)
    current_user.must_change_password = False
    db.session.commit()
    
    flash('密码修改成功', 'success')
    return redirect(url_for('auth.profile'))

@auth_bp.route('/api/check-username')
def check_username():
    username = request.args.get('username')
    if not username:
        return jsonify({'available': False})
    
    exists = User.query.filter_by(username=username).first() is not None
    return jsonify({'available': not exists})

@auth_bp.route('/api/check-email')
def check_email():
    email = request.args.get('email')
    if not email:
        return jsonify({'available': False})
    
    exists = User.query.filter_by(email=email).first() is not None
    return jsonify({'available': not exists})

@auth_bp.route('/api/password-policy')
def password_policy():
    """获取当前密码策略配置（供前端实时校验使用）"""
    return jsonify(get_password_policy_config())
