import io
import pandas as pd
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required
from app import db
from app.models import Leaderboard
from app.utils.leaderboard_service import update_leaderboard, LeaderboardCache
from app.routes.admin import admin_bp, admin_required

@admin_bp.route('/leaderboard')
@login_required
@admin_required
def leaderboard_manage():
    page = request.args.get('page', 1, type=int)
    period = request.args.get('period', 'all_time')
    category = request.args.get('category', 'total_points')
    
    query = Leaderboard.query.filter_by(period=period, category=category)
    pagination = query.order_by(Leaderboard.rank).paginate(page=page, per_page=50)
    
    return render_template('admin/leaderboard.html', 
                          pagination=pagination,
                          period=period,
                          category=category)

@admin_bp.route('/leaderboard/update', methods=['POST'])
@login_required
@admin_required
def update_leaderboard_route():
    period = request.form.get('period', 'all_time')
    category = request.form.get('category', 'total_points')
    
    try:
        update_leaderboard(period=period, category=category)
        flash('排行榜更新成功', 'success')
    except Exception as e:
        flash(f'排行榜更新失败: {str(e)}', 'error')
    
    return redirect(url_for('admin.leaderboard_manage', period=period, category=category))

@admin_bp.route('/leaderboard/clear-cache', methods=['POST'])
@login_required
@admin_required
def clear_leaderboard_cache():
    LeaderboardCache.clear_cache()
    flash('排行榜缓存已清除', 'success')
    return redirect(url_for('admin.leaderboard_manage'))

@admin_bp.route('/leaderboard/export')
@login_required
@admin_required
def export_leaderboard():
    from app.models import User
    from app.utils.leaderboard_service import get_leaderboard_data
    
    category = request.args.get('category', 'total_points')
    
    periods = [
        ('all_time', '总榜'),
        ('monthly', '月榜'),
        ('weekly', '周榜'),
        ('daily', '日榜')
    ]
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for period_key, period_name in periods:
            result = get_leaderboard_data(
                category=category,
                period=period_key,
                page=1,
                per_page=10000
            )
            
            data = []
            for entry in result['entries']:
                user = entry['user']
                data.append({
                    '排名': entry['rank'],
                    '用户名': user.username,
                    '昵称': user.nickname or '',
                    '学校': user.school or '',
                    '年级': user.grade or '',
                    '班级': user.class_name or '',
                    '积分': entry['score'],
                    '段位': user.current_tier.display_name if user.current_tier else '未定段'
                })
            
            df = pd.DataFrame(data)
            df.to_excel(writer, index=False, sheet_name=period_name)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'排行榜_{category}_{pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    )
