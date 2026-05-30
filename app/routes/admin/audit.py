import io
import json
from datetime import datetime, timedelta
from flask import render_template, request, send_file
from flask_login import login_required, current_user
from app import db
from app.models import User, PointRecord
from app.routes.admin import admin_bp, admin_required

@admin_bp.route('/points/audit')
@login_required
@admin_required
def points_audit():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    if per_page not in (10, 20, 50, 100, 200):
        per_page = 20
    user_id = request.args.get('user_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    reason_filter = request.args.get('reason', '')

    query = PointRecord.query

    if user_id:
        query = query.filter_by(user_id=user_id)
    if start_date:
        query = query.filter(PointRecord.created_at >= start_date)
    if end_date:
        query = query.filter(PointRecord.created_at <= end_date + ' 23:59:59')
    if reason_filter:
        query = query.filter_by(reason=reason_filter)

    filtered_query = query

    pagination = query.order_by(PointRecord.created_at.desc()).paginate(page=page, per_page=per_page)

    all_filtered_records = filtered_query.all()

    total_issued = sum(r.points for r in all_filtered_records if r.points > 0)
    total_deducted = abs(sum(r.points for r in all_filtered_records if r.points < 0))
    net_change = total_issued - total_deducted
    record_count = len(all_filtered_records)
    active_users_count = len(set(r.user_id for r in all_filtered_records))

    reason_stats = {}
    for r in all_filtered_records:
        label = PointRecord.REASONS.get(r.reason, r.reason)
        if label not in reason_stats:
            reason_stats[label] = {'count': 0, 'points': 0, 'key': r.reason}
        reason_stats[label]['count'] += 1
        reason_stats[label]['points'] += r.points
    reason_list = sorted(reason_stats.values(), key=lambda x: x['count'], reverse=True)

    trend_data = {}
    for r in all_filtered_records:
        date_key = r.created_at.strftime('%Y-%m-%d')
        if date_key not in trend_data:
            trend_data[date_key] = {'date': date_key, 'issued': 0, 'deducted': 0}
        if r.points > 0:
            trend_data[date_key]['issued'] += r.points
        else:
            trend_data[date_key]['deducted'] += abs(r.points)
    trend_list = sorted(trend_data.values(), key=lambda x: x['date'])

    top_users = {}
    for r in all_filtered_records:
        uid = r.user_id
        if uid not in top_users:
            uname = r.user.nickname or r.user.username
            top_users[uid] = {'id': uid, 'name': uname, 'points': 0, 'count': 0}
        top_users[uid]['points'] += r.points
        top_users[uid]['count'] += 1
    top_list = sorted(top_users.values(), key=lambda x: x['points'], reverse=True)[:10]

    reason_options = list(PointRecord.REASONS.items())

    users = User.query.filter_by(is_active=True).order_by(User.nickname).all()

    return render_template(
        'admin/points_audit.html',
        pagination=pagination,
        users=users,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        reason_filter=reason_filter,
        per_page=per_page,
        total_issued=total_issued,
        total_deducted=total_deducted,
        net_change=net_change,
        record_count=record_count,
        active_users_count=active_users_count,
        reason_list=reason_list,
        trend_list=trend_list,
        top_list=top_list,
        reason_options=reason_options,
        has_filters=(user_id or start_date or end_date or reason_filter)
    )

@admin_bp.route('/points/audit/export')
@login_required
@admin_required
def export_points_audit():
    import pandas as pd
    user_id = request.args.get('user_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    reason_filter = request.args.get('reason', '')

    query = PointRecord.query

    if user_id:
        query = query.filter_by(user_id=user_id)
    if start_date:
        query = query.filter(PointRecord.created_at >= start_date)
    if end_date:
        query = query.filter(PointRecord.created_at <= end_date + ' 23:59:59')
    if reason_filter:
        query = query.filter_by(reason=reason_filter)

    records = query.order_by(PointRecord.created_at.desc()).all()

    data = []
    for record in records:
        data.append({
            'ID': record.id,
            '用户': record.user.nickname or record.user.username,
            '用户名': record.user.username,
            '积分变化': record.points,
            '原因': PointRecord.REASONS.get(record.reason, record.reason),
            '时间': record.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })

    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='积分审计')
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'积分审计_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    )
