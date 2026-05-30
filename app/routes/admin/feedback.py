from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.question_feedback import QuestionFeedback
from app.models import Question, User
from app.models.notification import UserNotification
from app.routes.admin import admin_bp, admin_required, role_required
from app.utils.op_log import log_operation
from datetime import datetime, timezone

def _send_feedback_notification(user_id, feedback_id, action, admin_reply, points_awarded):
    """发送反馈处理通知给用户"""
    from app.models.question_feedback import QuestionFeedback
    
    feedback = QuestionFeedback.query.get(feedback_id)
    if not feedback:
        return
    
    question_type_label = QuestionFeedback.FEEDBACK_TYPES.get(
        feedback.feedback_type, 
        feedback.feedback_type
    )
    
    if action == 'resolved':
        title = '题目反馈已处理'
        
        content_parts = [f'您提交的【{question_type_label}】反馈已被处理。']
        
        if admin_reply:
            content_parts.append(f'\n\n管理员回复：{admin_reply}')
        
        if points_awarded > 0:
            content_parts.append(f'\n\n🎉 感谢您的宝贵反馈，奖励您 {points_awarded} 积分！')
        else:
            content_parts.append('\n\n感谢您的反馈！')
        
        content = ''.join(content_parts)
        
        notification = UserNotification(
            user_id=user_id,
            notification_type='feedback_resolved',
            title=title,
            content=content,
            related_id=feedback_id,
            related_type='question_feedback'
        )
        db.session.add(notification)
        
    elif action == 'rejected':
        title = '题目反馈未通过'
        content = f'您提交的【{question_type_label}】反馈未通过审核。'
        
        if admin_reply:
            content += f'\n\n管理员回复：{admin_reply}'
        
        notification = UserNotification(
            user_id=user_id,
            notification_type='feedback_rejected',
            title=title,
            content=content,
            related_id=feedback_id,
            related_type='question_feedback'
        )
        db.session.add(notification)

@admin_bp.route('/feedback')
@login_required
@role_required('admin', 'teacher')
def feedback_list():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', 'pending')
    feedback_type = request.args.get('feedback_type')
    
    query = QuestionFeedback.query
    
    if status:
        query = query.filter_by(status=status)
    
    if feedback_type:
        query = query.filter_by(feedback_type=feedback_type)
    
    pagination = query.order_by(QuestionFeedback.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    feedback_stats = db.session.query(
        QuestionFeedback.status,
        db.func.count(QuestionFeedback.id)
    ).group_by(QuestionFeedback.status).all()
    
    type_stats = db.session.query(
        QuestionFeedback.feedback_type,
        db.func.count(QuestionFeedback.id)
    ).group_by(QuestionFeedback.feedback_type).all()
    
    return render_template(
        'admin/feedback.html',
        pagination=pagination,
        feedback_stats=dict(feedback_stats),
        type_stats=dict(type_stats),
        current_status=status,
        current_type=feedback_type,
        QuestionFeedback=QuestionFeedback
    )

@admin_bp.route('/feedback/<int:feedback_id>')
@login_required
@role_required('admin', 'teacher')
def feedback_detail(feedback_id):
    feedback = QuestionFeedback.query.get_or_404(feedback_id)
    
    from app.models import Subject, Chapter
    
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()
    chapters = Chapter.query.filter_by(is_active=True).order_by(Chapter.order).all()
    
    return render_template(
        'admin/feedback_detail.html', 
        feedback=feedback, 
        QuestionFeedback=QuestionFeedback,
        subjects=subjects,
        chapters=chapters
    )

@admin_bp.route('/feedback/<int:feedback_id>/resolve', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
def feedback_resolve(feedback_id):
    feedback = QuestionFeedback.query.get_or_404(feedback_id)
    
    if feedback.status == 'resolved':
        return jsonify({'success': False, 'message': '该反馈已经被处理'}), 400
    
    admin_reply = request.form.get('admin_reply', '')
    points_awarded = request.form.get('points_awarded', 0, type=int)
    
    old_status = feedback.status
    feedback.status = 'resolved'
    feedback.admin_reply = admin_reply if admin_reply else None
    feedback.points_awarded = points_awarded
    feedback.resolved_at = datetime.now(timezone.utc)
    feedback.resolved_by = current_user.id
    
    if points_awarded > 0:
        user = User.query.get(feedback.user_id)
        if user:
            user.add_points(points_awarded, f'feedback_reward_{feedback_id}')
    
    db.session.commit()
    
    if old_status != 'resolved':
        _send_feedback_notification(
            feedback.user_id,
            feedback.id,
            'resolved',
            admin_reply,
            points_awarded
        )
    
    log_operation(
        'resolve',
        'question_feedback',
        detail=f'处理反馈 #{feedback_id}，奖励积分: {points_awarded}'
    )
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': '反馈已标记为已解决'
        })
    
    flash('反馈已标记为已解决', 'success')
    return redirect(url_for('admin.feedback_list'))

@admin_bp.route('/feedback/<int:feedback_id>/reject', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
def feedback_reject(feedback_id):
    feedback = QuestionFeedback.query.get_or_404(feedback_id)
    
    if feedback.status != 'pending':
        return jsonify({'success': False, 'message': '只能拒绝待处理的反馈'}), 400
    
    admin_reply = request.form.get('admin_reply', '')
    
    feedback.status = 'rejected'
    feedback.admin_reply = admin_reply if admin_reply else None
    feedback.resolved_at = datetime.now(timezone.utc)
    feedback.resolved_by = current_user.id
    
    db.session.flush()
    
    _send_feedback_notification(
        feedback.user_id,
        feedback.id,
        'rejected',
        admin_reply,
        0
    )
    
    db.session.commit()
    
    log_operation(
        'reject',
        'question_feedback',
        detail=f'拒绝反馈 #{feedback_id}'
    )
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': '反馈已拒绝'
        })
    
    flash('反馈已拒绝', 'success')
    return redirect(url_for('admin.feedback_list'))

@admin_bp.route('/feedback/<int:feedback_id>/processing', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
def feedback_processing(feedback_id):
    feedback = QuestionFeedback.query.get_or_404(feedback_id)
    
    if feedback.status != 'pending':
        return jsonify({'success': False, 'message': '只能将待处理的反馈标记为处理中'}), 400
    
    feedback.status = 'processing'
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': '反馈已标记为处理中'
        })
    
    flash('反馈已标记为处理中', 'success')
    return redirect(url_for('admin.feedback_detail', feedback_id=feedback_id))

@admin_bp.route('/feedback/batch-action', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
def feedback_batch_action():
    action = request.form.get('action')
    feedback_ids_str = request.form.get('feedback_ids', '')
    
    if not feedback_ids_str:
        return jsonify({'success': False, 'message': '请选择要操作的反馈'}), 400
    
    try:
        feedback_ids = [int(id) for id in feedback_ids_str.split(',')]
    except ValueError:
        return jsonify({'success': False, 'message': '反馈ID格式错误'}), 400
    
    feedbacks = QuestionFeedback.query.filter(QuestionFeedback.id.in_(feedback_ids)).all()
    
    count = 0
    if action == 'resolve':
        points_awarded = request.form.get('points_awarded', 0, type=int)
        admin_reply = request.form.get('admin_reply', '')
        
        for feedback in feedbacks:
            if feedback.status == 'pending':
                feedback.status = 'resolved'
                feedback.admin_reply = admin_reply if admin_reply else None
                feedback.points_awarded = points_awarded
                feedback.resolved_at = datetime.now(timezone.utc)
                feedback.resolved_by = current_user.id
                
                if points_awarded > 0:
                    user = User.query.get(feedback.user_id)
                    if user:
                        user.add_points(points_awarded, f'feedback_reward_{feedback.id}')
                count += 1
    
    elif action == 'reject':
        admin_reply = request.form.get('admin_reply', '')
        
        for feedback in feedbacks:
            if feedback.status == 'pending':
                feedback.status = 'rejected'
                feedback.admin_reply = admin_reply if admin_reply else None
                feedback.resolved_at = datetime.now(timezone.utc)
                feedback.resolved_by = current_user.id
                count += 1
    
    elif action == 'processing':
        for feedback in feedbacks:
            if feedback.status == 'pending':
                feedback.status = 'processing'
                count += 1
    
    db.session.commit()
    
    log_operation(
        'batch_' + action,
        'question_feedback',
        detail=f'批量处理 {count} 条反馈'
    )
    
    return jsonify({
        'success': True,
        'message': f'成功{QuestionFeedback.STATUS_LABELS.get(action, "处理")} {count} 条反馈'
    })
