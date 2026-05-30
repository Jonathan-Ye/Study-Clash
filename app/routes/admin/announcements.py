from datetime import datetime, timezone
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.announcement import Announcement, AnnouncementRead
from app.models import User
from app.routes.admin import admin_bp, admin_required
from app.utils.op_log import log_operation
from app.utils.common import make_aware


@admin_bp.route('/announcements')
@login_required
@admin_required
def announcements():
    """系统公告列表"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status')
    priority_filter = request.args.get('priority')

    query = Announcement.query

    if status_filter:
        query = query.filter_by(status=status_filter)
    if priority_filter:
        query = query.filter_by(priority=priority_filter)

    pagination = query.order_by(Announcement.created_at.desc()).paginate(page=page, per_page=15)

    # 计算已读统计
    total_active_users = User.query.filter_by(is_active=True).count()
    for a in pagination.items:
        a.effective_status = Announcement.get_effective_status(a)
        a.read_count = AnnouncementRead.query.filter_by(announcement_id=a.id).count()
        a.total_users = total_active_users
        a.read_rate = round(a.read_count / total_active_users * 100, 1) if total_active_users > 0 else 0

    breadcrumb = [
        {'label': '系统管理'},
        {'label': '系统公告'}
    ]

    return render_template('admin/announcements.html',
                          pagination=pagination,
                          breadcrumb=breadcrumb,
                          status_filter=status_filter,
                          priority_filter=priority_filter)


@admin_bp.route('/announcements/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_announcement():
    """创建公告"""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        priority = request.form.get('priority', 'normal')
        display_position = request.form.get('display_position', 'top_banner')
        publish_at_str = request.form.get('publish_at', '').strip()
        expire_at_str = request.form.get('expire_at', '').strip()

        if not title or not content:
            flash('标题和内容不能为空', 'error')
            return render_template('admin/announcement_form.html',
                                  breadcrumb=[{'label': '系统管理'}, {'label': '系统公告'}, {'label': '新建公告'}])

        publish_at = None
        expire_at = None

        if publish_at_str:
            try:
                publish_at = datetime.strptime(publish_at_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash('发布时间格式错误', 'error')
                return render_template('admin/announcement_form.html',
                                      breadcrumb=[{'label': '系统管理'}, {'label': '系统公告'}, {'label': '新建公告'}])

        if expire_at_str:
            try:
                expire_at = datetime.strptime(expire_at_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash('过期时间格式错误', 'error')
                return render_template('admin/announcement_form.html',
                                      breadcrumb=[{'label': '系统管理'}, {'label': '系统公告'}, {'label': '新建公告'}])

        if expire_at and publish_at and expire_at < publish_at:
            flash('过期时间不能早于发布时间', 'error')
            return render_template('admin/announcement_form.html',
                                  breadcrumb=[{'label': '系统管理'}, {'label': '系统公告'}, {'label': '新建公告'}])

        # 确定初始状态
        now = datetime.now(timezone.utc)
        if publish_at and make_aware(publish_at) > now:
            status = 'pending'
        else:
            status = 'published'

        announcement = Announcement(
            title=title,
            content=content,
            priority=priority,
            display_position=display_position,
            status=status,
            publish_at=publish_at,
            expire_at=expire_at,
            created_by=current_user.id
        )
        db.session.add(announcement)
        db.session.commit()

        log_operation('create', 'announcement', target_id=announcement.id,
                      target_name=title, detail=f'优先级:{priority} 位置:{display_position}')
        flash('公告创建成功', 'success')
        return redirect(url_for('admin.announcements'))

    breadcrumb = [
        {'label': '系统管理'},
        {'label': '系统公告'},
        {'label': '新建公告'}
    ]
    return render_template('admin/announcement_form.html', breadcrumb=breadcrumb)


@admin_bp.route('/announcements/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_announcement(id):
    """编辑公告"""
    announcement = Announcement.query.get_or_404(id)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        priority = request.form.get('priority', 'normal')
        display_position = request.form.get('display_position', 'top_banner')
        publish_at_str = request.form.get('publish_at', '').strip()
        expire_at_str = request.form.get('expire_at', '').strip()

        if not title or not content:
            flash('标题和内容不能为空', 'error')
            return render_template('admin/announcement_form.html',
                                  announcement=announcement,
                                  breadcrumb=[{'label': '系统管理'}, {'label': '系统公告'}, {'label': '编辑公告'}])

        publish_at = None
        expire_at = None

        if publish_at_str:
            try:
                publish_at = datetime.strptime(publish_at_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                pass
        if expire_at_str:
            try:
                expire_at = datetime.strptime(expire_at_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                pass

        if expire_at and publish_at and expire_at < publish_at:
            flash('过期时间不能早于发布时间', 'error')
            return render_template('admin/announcement_form.html',
                                  announcement=announcement,
                                  breadcrumb=[{'label': '系统管理'}, {'label': '系统公告'}, {'label': '编辑公告'}])

        announcement.title = title
        announcement.content = content
        announcement.priority = priority
        announcement.display_position = display_position
        announcement.publish_at = publish_at
        announcement.expire_at = expire_at

        # 重新计算状态
        now = datetime.now(timezone.utc)
        if expire_at and now > make_aware(expire_at):
            announcement.status = 'expired'
        elif publish_at and now < make_aware(publish_at):
            announcement.status = 'pending'
        else:
            announcement.status = 'published'

        db.session.commit()

        log_operation('update', 'announcement', target_id=id, target_name=title)
        flash('公告更新成功', 'success')
        return redirect(url_for('admin.announcements'))

    breadcrumb = [
        {'label': '系统管理'},
        {'label': '系统公告'},
        {'label': '编辑公告'}
    ]
    return render_template('admin/announcement_form.html',
                          announcement=announcement,
                          breadcrumb=breadcrumb)


@admin_bp.route('/announcements/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_announcement(id):
    """删除公告"""
    announcement = Announcement.query.get_or_404(id)
    title = announcement.title
    db.session.delete(announcement)
    db.session.commit()

    log_operation('delete', 'announcement', target_id=id, target_name=title)
    flash('公告删除成功', 'success')
    return redirect(url_for('admin.announcements'))


@admin_bp.route('/announcements/<int:id>/mark-read', methods=['POST'])
@login_required
def mark_announcement_read(id):
    """标记公告为已读"""
    announcement = Announcement.query.get_or_404(id)
    is_new = AnnouncementRead.mark_read(id, current_user.id)
    if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
        return jsonify({'success': True, 'is_new': is_new})
    return redirect(request.referrer or url_for('main.index'))


@admin_bp.route('/announcements/<int:id>/read-details')
@login_required
@admin_required
def announcement_read_details(id):
    """查看公告已读详情"""
    announcement = Announcement.query.get_or_404(id)
    reads = AnnouncementRead.query.filter_by(announcement_id=id).order_by(AnnouncementRead.read_at.desc()).all()

    read_details = []
    for r in reads:
        user = User.query.get(r.user_id)
        if user:
            read_details.append({
                'username': user.username,
                'nickname': user.nickname or user.username,
                'read_at': r.read_at
            })

    total_active_users = User.query.filter_by(is_active=True).count()
    read_count = len(read_details)
    read_rate = round(read_count / total_active_users * 100, 1) if total_active_users > 0 else 0

    breadcrumb = [
        {'label': '系统管理'},
        {'label': '系统公告', 'endpoint': 'admin.announcements'},
        {'label': f'已读详情 - {announcement.title}'}
    ]

    return render_template('admin/announcement_read_details.html',
                          announcement=announcement,
                          read_details=read_details,
                          read_count=read_count,
                          total_users=total_active_users,
                          read_rate=read_rate,
                          breadcrumb=breadcrumb)
