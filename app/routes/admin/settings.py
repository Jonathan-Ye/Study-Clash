import os
from datetime import timedelta
from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required
from app import db
from app.models import SystemSetting
from app.routes.admin import admin_bp, admin_required
from app.utils.op_log import log_operation
from app.utils.file_validator import validate_image_file

@admin_bp.route('/settings')
@login_required
@admin_required
def settings():
    current_logo = SystemSetting.get('site_logo', 'logo-small.png')
    session_lifetime_hours = int(SystemSetting.get('session_lifetime_hours', 
                          current_app.config.get('SESSION_LIFETIME_HOURS', 2)))
    
    wrong_question_config = {
        'consecutive_correct': int(SystemSetting.get('wrong_consecutive_correct', 3)),
        'review_points': int(SystemSetting.get('wrong_review_points', 5)),
        'max_review_per_day': int(SystemSetting.get('wrong_max_review_per_day', 50)),
        'enable_spaced_review': SystemSetting.get('wrong_enable_spaced_review', 'true') == 'true',
    }
    
    site_info = {
        'site_name': SystemSetting.get('site_name', 'Study Clash'),
        'site_desc': SystemSetting.get('site_desc', '让学习变得更有趣，让竞争激发潜能。通过游戏化的方式提升学习效率。'),
        'contact_email': SystemSetting.get('contact_email', 'contact@studyclash.com'),
        'contact_phone': SystemSetting.get('contact_phone', '400-123-4567'),
        'copyright': SystemSetting.get('copyright', '© 2024 Study Clash. All rights reserved.'),
        'icp': SystemSetting.get('icp', ''),
        'footer_slogan': SystemSetting.get('footer_slogan', 'Made with <i class="bi bi-heart-fill text-danger"></i> for learners'),
        
        'social_wechat': SystemSetting.get('social_wechat', ''),
        'social_qq': SystemSetting.get('social_qq', ''),
        'social_weibo': SystemSetting.get('social_weibo', ''),
        'social_github': SystemSetting.get('social_github', ''),
        'social_email': SystemSetting.get('social_email', ''),
        
        'show_site_info': SystemSetting.get('show_site_info', 'true') == 'true',
        'show_game_modes': SystemSetting.get('show_game_modes', 'true') == 'true',
        'show_features': SystemSetting.get('show_features', 'true') == 'true',
        'show_help': SystemSetting.get('show_help', 'true') == 'true',
        'show_contact': SystemSetting.get('show_contact', 'true') == 'true',
        'show_contact_email': SystemSetting.get('show_contact_email', 'true') == 'true',
        'show_contact_phone': SystemSetting.get('show_contact_phone', 'true') == 'true',
        'show_copyright': SystemSetting.get('show_copyright', 'true') == 'true',
        'show_icp': SystemSetting.get('show_icp', 'false') == 'true',
        'show_social': SystemSetting.get('show_social', 'false') == 'true',
        'show_slogan': SystemSetting.get('show_slogan', 'true') == 'true',
    }
    
    security_config = {
        'registration_enabled': SystemSetting.get('registration_enabled', 'true') == 'true',
        'password_policy_enabled': SystemSetting.get('password_policy_enabled', 'false') == 'true',
        'password_min_length': int(SystemSetting.get('password_min_length', '8')),
        'password_require_uppercase': SystemSetting.get('password_require_uppercase', 'true') == 'true',
        'password_require_lowercase': SystemSetting.get('password_require_lowercase', 'true') == 'true',
        'password_require_digit': SystemSetting.get('password_require_digit', 'true') == 'true',
        'password_require_special': SystemSetting.get('password_require_special', 'true') == 'true',
        'max_login_attempts': int(SystemSetting.get('max_login_attempts', '5')),
        'lockout_duration': int(SystemSetting.get('lockout_duration', '30')),
    }
    
    return render_template('admin/settings.html', 
                          points_config=current_app.config.get('POINTS_CONFIG', {}),
                          room_expire_minutes=current_app.config.get('ROOM_EXPIRE_MINUTES', 20),
                          single_wrong_chances=current_app.config.get('SINGLE_CHALLENGE_WRONG_CHANCES', 3),
                          active_game_timeout=int(SystemSetting.get('active_game_timeout', '30')),
                          current_logo=current_logo,
                          session_lifetime_hours=session_lifetime_hours,
                          wrong_question_config=wrong_question_config,
                          site_info=site_info,
                          security_config=security_config)

@admin_bp.route('/settings/session', methods=['POST'])
@login_required
@admin_required
def update_session_settings():
    session_lifetime_hours = request.form.get('session_lifetime_hours', 2, type=int)
    if session_lifetime_hours < 1:
        session_lifetime_hours = 1
    if session_lifetime_hours > 168:
        session_lifetime_hours = 168
    
    SystemSetting.set('session_lifetime_hours', str(session_lifetime_hours), '用户会话有效时长（小时）')
    current_app.config['SESSION_LIFETIME_HOURS'] = session_lifetime_hours
    current_app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=session_lifetime_hours)
    
    flash(f'用户在线时长已更新为 {session_lifetime_hours} 小时', 'success')
    log_operation('config_change', 'setting', detail=f'会话时长={session_lifetime_hours}小时')
    return redirect(url_for('admin.settings'))

@admin_bp.route('/settings/logo', methods=['POST'])
@login_required
@admin_required
def update_logo():
    if 'logo' not in request.files:
        flash('没有选择文件', 'error')
        return redirect(url_for('admin.settings'))
    
    file = request.files['logo']
    if file.filename == '':
        flash('没有选择文件', 'error')
        return redirect(url_for('admin.settings'))
    
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'svg'}
    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    
    if file_ext not in allowed_extensions:
        flash('只允许上传图片文件 (PNG, JPG, JPEG, GIF, SVG)', 'error')
        return redirect(url_for('admin.settings'))
    
    # 文件内容安全校验（Magic Bytes + SVG安全检测）
    is_valid, error_msg = validate_image_file(file, allowed_extensions)
    if not is_valid:
        flash(error_msg, 'error')
        try:
            log_operation('upload_reject', 'security', detail=f'Logo上传拒绝: {error_msg}')
        except Exception:
            pass
        return redirect(url_for('admin.settings'))
    
    filename = f'logo_custom.{file_ext}'
    upload_path = os.path.join(current_app.root_path, 'static', 'images', filename)
    
    try:
        file.save(upload_path)
        SystemSetting.set('site_logo', filename, '网站Logo')
        log_operation('config_change', 'setting', detail=f'Logo更新为{filename}')
        flash('Logo更新成功', 'success')
    except Exception as e:
        flash(f'上传失败: {str(e)}', 'error')
    
    return redirect(url_for('admin.settings'))

@admin_bp.route('/settings/logo/reset', methods=['POST'])
@login_required
@admin_required
def reset_logo():
    custom_logo = SystemSetting.get('site_logo')
    if custom_logo and custom_logo.startswith('logo_custom'):
        upload_path = os.path.join(current_app.root_path, 'static', 'images', custom_logo)
        if os.path.exists(upload_path):
            os.remove(upload_path)
    
    SystemSetting.set('site_logo', 'logo-small.png', '网站Logo')
    log_operation('config_change', 'setting', detail='恢复默认Logo')
    flash('已恢复默认Logo', 'success')
    return redirect(url_for('admin.settings'))

@admin_bp.route('/settings/room', methods=['POST'])
@login_required
@admin_required
def update_room_settings():
    room_expire_minutes = request.form.get('room_expire_minutes', 20, type=int)
    if room_expire_minutes < 1:
        room_expire_minutes = 1
    if room_expire_minutes > 60:
        room_expire_minutes = 60
    
    current_app.config['ROOM_EXPIRE_MINUTES'] = room_expire_minutes
    
    log_operation('config_change', 'setting', detail=f'房间过期时间={room_expire_minutes}分钟')
    flash(f'房间过期时间已更新为 {room_expire_minutes} 分钟', 'success')
    return redirect(url_for('admin.settings'))

@admin_bp.route('/settings/single-challenge', methods=['POST'])
@login_required
@admin_required
def update_single_challenge_settings():
    single_wrong_chances = request.form.get('single_wrong_chances', 3, type=int)
    if single_wrong_chances < 1:
        single_wrong_chances = 1
    if single_wrong_chances > 10:
        single_wrong_chances = 10
    
    current_app.config['SINGLE_CHALLENGE_WRONG_CHANCES'] = single_wrong_chances
    
    log_operation('config_change', 'setting', detail=f'单人挑战错误机会={single_wrong_chances}次')
    flash(f'单人挑战错误机会已更新为 {single_wrong_chances} 次', 'success')
    return redirect(url_for('admin.settings'))

@admin_bp.route('/settings/points', methods=['POST'])
@login_required
@admin_required
def update_points_settings():
    points_config = {
        'single_correct': request.form.get('single_correct', 10, type=int),
        'battle_win': request.form.get('battle_win', 50, type=int),
        'four_first': request.form.get('four_first', 100, type=int),
        'four_second': request.form.get('four_second', 50, type=int),
        'four_third': request.form.get('four_third', 30, type=int),
        'four_fourth': request.form.get('four_fourth', 10, type=int),
        'review_correct': request.form.get('review_correct', 5, type=int),
        'daily_login': request.form.get('daily_login', 20, type=int),
        'streak_bonus': request.form.get('streak_bonus', 10, type=int),
    }
    
    current_app.config['POINTS_CONFIG'] = points_config
    
    log_operation('config_change', 'setting', detail=f'积分设置更新')
    flash('积分设置已更新', 'success')
    return redirect(url_for('admin.settings'))

@admin_bp.route('/settings/wrong-question', methods=['POST'])
@login_required
@admin_required
def update_wrong_question_settings():
    consecutive_correct = request.form.get('wrong_consecutive_correct', 3, type=int)
    if consecutive_correct < 1:
        consecutive_correct = 1
    if consecutive_correct > 10:
        consecutive_correct = 10
    SystemSetting.set('wrong_consecutive_correct', str(consecutive_correct), '错题掌握需要连续正确次数')
    
    review_points = request.form.get('wrong_review_points', 5, type=int)
    if review_points < 0:
        review_points = 0
    if review_points > 100:
        review_points = 100
    SystemSetting.set('wrong_review_points', str(review_points), '错题复习正确获得积分')
    
    max_review_per_day = request.form.get('wrong_max_review_per_day', 50, type=int)
    if max_review_per_day < 10:
        max_review_per_day = 10
    if max_review_per_day > 200:
        max_review_per_day = 200
    SystemSetting.set('wrong_max_review_per_day', str(max_review_per_day), '每日最大复习数量')
    
    enable_spaced_review = 'true' if request.form.get('wrong_enable_spaced_review') == 'on' else 'false'
    SystemSetting.set('wrong_enable_spaced_review', enable_spaced_review, '是否启用间隔复习')
    
    log_operation('config_change', 'setting', detail='错题本设置更新')
    flash('错题本设置已更新', 'success')
    return redirect(url_for('admin.settings'))

@admin_bp.route('/settings/site-info', methods=['POST'])
@login_required
@admin_required
def update_site_info_settings():
    site_name = request.form.get('site_name', 'Study Clash').strip()
    SystemSetting.set('site_name', site_name, '网站名称')
    
    site_desc = request.form.get('site_desc', '').strip()
    SystemSetting.set('site_desc', site_desc, '网站描述')
    
    contact_email = request.form.get('contact_email', '').strip()
    SystemSetting.set('contact_email', contact_email, '联系邮箱')
    
    contact_phone = request.form.get('contact_phone', '').strip()
    SystemSetting.set('contact_phone', contact_phone, '联系电话')
    
    copyright_text = request.form.get('copyright', '').strip()
    SystemSetting.set('copyright', copyright_text, '版权信息')
    
    icp = request.form.get('icp', '').strip()
    SystemSetting.set('icp', icp, 'ICP备案号')
    
    footer_slogan = request.form.get('footer_slogan', '').strip()
    SystemSetting.set('footer_slogan', footer_slogan, '页脚标语')
    
    social_wechat = request.form.get('social_wechat', '').strip()
    SystemSetting.set('social_wechat', social_wechat, '微信链接')
    
    social_qq = request.form.get('social_qq', '').strip()
    SystemSetting.set('social_qq', social_qq, 'QQ链接')
    
    social_weibo = request.form.get('social_weibo', '').strip()
    SystemSetting.set('social_weibo', social_weibo, '微博链接')
    
    social_github = request.form.get('social_github', '').strip()
    SystemSetting.set('social_github', social_github, 'GitHub链接')
    
    social_email = request.form.get('social_email', '').strip()
    SystemSetting.set('social_email', social_email, '社交邮箱链接')
    
    show_site_info = 'true' if request.form.get('show_site_info') == 'on' else 'false'
    SystemSetting.set('show_site_info', show_site_info, '显示网站介绍')
    
    show_game_modes = 'true' if request.form.get('show_game_modes') == 'on' else 'false'
    SystemSetting.set('show_game_modes', show_game_modes, '显示游戏模式')
    
    show_features = 'true' if request.form.get('show_features') == 'on' else 'false'
    SystemSetting.set('show_features', show_features, '显示功能')
    
    show_help = 'true' if request.form.get('show_help') == 'on' else 'false'
    SystemSetting.set('show_help', show_help, '显示帮助支持')
    
    show_contact = 'true' if request.form.get('show_contact') == 'on' else 'false'
    SystemSetting.set('show_contact', show_contact, '显示联系方式')
    
    show_contact_email = 'true' if request.form.get('show_contact_email') == 'on' else 'false'
    SystemSetting.set('show_contact_email', show_contact_email, '显示联系邮箱')
    
    show_contact_phone = 'true' if request.form.get('show_contact_phone') == 'on' else 'false'
    SystemSetting.set('show_contact_phone', show_contact_phone, '显示联系电话')
    
    show_copyright = 'true' if request.form.get('show_copyright') == 'on' else 'false'
    SystemSetting.set('show_copyright', show_copyright, '显示版权信息')
    
    show_icp = 'true' if request.form.get('show_icp') == 'on' else 'false'
    SystemSetting.set('show_icp', show_icp, '显示ICP备案')
    
    show_social = 'true' if request.form.get('show_social') == 'on' else 'false'
    SystemSetting.set('show_social', show_social, '显示社交媒体')
    
    show_slogan = 'true' if request.form.get('show_slogan') == 'on' else 'false'
    SystemSetting.set('show_slogan', show_slogan, '显示页脚标语')
    
    log_operation('config_change', 'setting', detail='网站信息设置更新')
    flash('网站信息设置已更新', 'success')
    return redirect(url_for('admin.settings'))

@admin_bp.route('/settings/security', methods=['POST'])
@login_required
@admin_required
def update_security_settings():
    registration_enabled = 'true' if request.form.get('registration_enabled') == 'on' else 'false'
    SystemSetting.set('registration_enabled', registration_enabled, '允许用户注册')
    
    password_policy_enabled = 'true' if request.form.get('password_policy_enabled') == 'on' else 'false'
    SystemSetting.set('password_policy_enabled', password_policy_enabled, '启用密码复杂度策略')
    
    password_min_length = request.form.get('password_min_length', 8, type=int)
    if password_min_length < 8:
        password_min_length = 8
    if password_min_length > 32:
        password_min_length = 32
    SystemSetting.set('password_min_length', str(password_min_length), '最小密码长度')
    
    password_require_uppercase = 'true' if request.form.get('password_require_uppercase') == 'on' else 'false'
    SystemSetting.set('password_require_uppercase', password_require_uppercase, '密码要求大写字母')
    
    password_require_lowercase = 'true' if request.form.get('password_require_lowercase') == 'on' else 'false'
    SystemSetting.set('password_require_lowercase', password_require_lowercase, '密码要求小写字母')
    
    password_require_digit = 'true' if request.form.get('password_require_digit') == 'on' else 'false'
    SystemSetting.set('password_require_digit', password_require_digit, '密码要求数字')
    
    password_require_special = 'true' if request.form.get('password_require_special') == 'on' else 'false'
    SystemSetting.set('password_require_special', password_require_special, '密码要求特殊字符')
    
    max_login_attempts = request.form.get('max_login_attempts', 5, type=int)
    if max_login_attempts < 3:
        max_login_attempts = 3
    if max_login_attempts > 10:
        max_login_attempts = 10
    SystemSetting.set('max_login_attempts', str(max_login_attempts), '最大登录尝试次数')
    
    lockout_duration = request.form.get('lockout_duration', 30, type=int)
    if lockout_duration < 5:
        lockout_duration = 5
    if lockout_duration > 60:
        lockout_duration = 60
    SystemSetting.set('lockout_duration', str(lockout_duration), '锁定时长（分钟）')
    
    log_operation('config_change', 'setting', detail='安全设置更新')
    flash('安全设置已更新', 'success')
    return redirect(url_for('admin.settings'))

@admin_bp.route('/settings/active-game-timeout', methods=['POST'])
@login_required
@admin_required
def update_active_game_timeout_settings():
    active_game_timeout = request.form.get('active_game_timeout', 30, type=int)
    if active_game_timeout < 1:
        active_game_timeout = 1
    if active_game_timeout > 120:
        active_game_timeout = 120
    
    SystemSetting.set('active_game_timeout', str(active_game_timeout), '活跃游戏超时时间（分钟），从游戏开始计算，超时后自动结束游戏')
    
    log_operation('config_change', 'setting', detail=f'活跃游戏超时时间={active_game_timeout}分钟')
    flash(f'活跃游戏超时时间已更新为 {active_game_timeout} 分钟', 'success')
    return redirect(url_for('admin.settings'))
