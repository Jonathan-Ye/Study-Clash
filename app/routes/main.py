from flask import Blueprint, render_template, redirect, url_for, jsonify, request, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, timezone
import os
import uuid
from app.models import Subject, Question, GameRecord, DailyStats, User
from app.models.question_feedback import QuestionFeedback
from app.models.notification import UserNotification
from app import db
from app.utils.common import allowed_avatar_file

main_bp = Blueprint('main', __name__)

@main_bp.route('/api/subjects')
@login_required
def api_subjects():
    subjects = Subject.query.filter_by(is_active=True).all()
    user_major = getattr(current_user, 'major', None) if current_user.is_authenticated else None
    filtered_subjects = [s for s in subjects if s.is_applicable_for_major(user_major)]
    return jsonify([{'id': s.id, 'name': s.name} for s in filtered_subjects])

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('main/index.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    subjects = Subject.query.filter_by(is_active=True).all()
    user_major = getattr(current_user, 'major', None)
    filtered_subjects = [s for s in subjects if s.is_applicable_for_major(user_major)]
    
    recent_games = GameRecord.query.filter_by(user_id=current_user.id)\
        .order_by(GameRecord.created_at.desc()).limit(5).all()
    
    from datetime import date
    today_stats = DailyStats.get_or_create(current_user.id)
    
    return render_template('main/dashboard.html', 
                          subjects=filtered_subjects,
                          recent_games=recent_games,
                          today_stats=today_stats)

@main_bp.route('/profile')
@login_required
def profile():
    user_id = request.args.get('user_id', type=int)
    if user_id and user_id != current_user.id:
        view_user = User.query.get_or_404(user_id)
        return render_template('main/profile.html', view_user=view_user)
    return render_template('main/profile.html')

@main_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if not current_user.can_edit_profile and not current_user.is_admin:
        flash('管理员已禁止您修改个人资料', 'error')
        return redirect(url_for('main.profile'))
    
    if request.method == 'POST':
        current_user.nickname = request.form.get('nickname', '')
        current_user.phone = request.form.get('phone', '')
        
        birthday_str = request.form.get('birthday', '')
        if birthday_str:
            try:
                current_user.birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        else:
            current_user.birthday = None
        
        db.session.commit()
        flash('资料更新成功', 'success')
        return redirect(url_for('main.profile'))
    
    return render_template('main/edit_profile.html')

@main_bp.route('/profile/avatar', methods=['POST'])
@login_required
def upload_avatar():
    if not current_user.can_edit_profile and not current_user.is_admin:
        return jsonify({'error': '管理员已禁止您修改个人资料'}), 403
    
    if 'avatar' not in request.files:
        return jsonify({'error': '没有选择文件'}), 400
    
    file = request.files['avatar']
    
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400
    
    if file and allowed_avatar_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{current_user.id}_{uuid.uuid4().hex[:8]}.{ext}"
        
        upload_dir = os.path.join(current_app.root_path, 'static', 'avatars')
        os.makedirs(upload_dir, exist_ok=True)
        
        if current_user.avatar and current_user.avatar != 'default.png':
            old_path = os.path.join(upload_dir, current_user.avatar)
            if os.path.exists(old_path):
                os.remove(old_path)
        
        file.save(os.path.join(upload_dir, filename))
        current_user.avatar = filename
        db.session.commit()
        
        return jsonify({'success': True, 'avatar_url': current_user.get_avatar_url()})
    
    return jsonify({'error': '不支持的文件格式'}), 400

@main_bp.route('/about')
def about():
    return render_template('main/about.html')

@main_bp.route('/help')
def help():
    return render_template('main/help.html')

@main_bp.route('/my-feedback')
@login_required
def my_feedback():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    status = request.args.get('status')
    
    query = QuestionFeedback.query.filter_by(user_id=current_user.id)
    
    if status:
        query = query.filter_by(status=status)
    
    pagination = query.order_by(QuestionFeedback.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('main/my_feedback.html', pagination=pagination, current_status=status, QuestionFeedback=QuestionFeedback)

@main_bp.route('/my-notifications')
@login_required
def my_notifications():
    notifications = UserNotification.query.filter_by(user_id=current_user.id)\
        .order_by(UserNotification.created_at.desc()).all()
    
    return render_template('main/my_notifications.html', notifications=notifications)

@main_bp.route('/notification/<int:notification_id>/mark-read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    notification = UserNotification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404()
    
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        db.session.commit()
    
    return jsonify({'success': True})

@main_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    UserNotification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({'is_read': True, 'read_at': datetime.now(timezone.utc)}, synchronize_session='fetch')
    
    db.session.commit()
    
    return jsonify({'success': True})
