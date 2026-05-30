from datetime import date, datetime, timedelta, timezone
from flask import render_template, jsonify, request
from flask_login import login_required
from app import db
from app.models import User, GameRecord, PointRecord
from app.routes.admin import admin_bp, admin_required


def get_date_range(column, target_date):
    """生成日期范围查询（PostgreSQL）"""
    next_date = target_date + timedelta(days=1)
    start_dt = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    end_dt = datetime(next_date.year, next_date.month, next_date.day, tzinfo=timezone.utc)
    return (column >= start_dt) & (column < end_dt)

@admin_bp.route('/statistics')
@login_required
@admin_required
def statistics():
    return render_template('admin/statistics.html')

@admin_bp.route('/api/statistics/overview')
@login_required
@admin_required
def api_statistics_overview():
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    
    today_stats = {
        'new_users': User.query.filter(get_date_range(User.created_at, today)).count(),
        'active_games': GameRecord.query.filter(get_date_range(GameRecord.created_at, today)).count(),
        'points_given': db.session.query(db.func.sum(PointRecord.points)).filter(
            get_date_range(PointRecord.created_at, today)
        ).scalar() or 0
    }
    
    week_stats = {
        'new_users': User.query.filter(
            User.created_at >= week_start
        ).count(),
        'active_games': GameRecord.query.filter(
            GameRecord.created_at >= week_start
        ).count(),
        'points_given': db.session.query(db.func.sum(PointRecord.points)).filter(
            PointRecord.created_at >= week_start
        ).scalar() or 0
    }
    
    month_stats = {
        'new_users': User.query.filter(
            User.created_at >= month_start
        ).count(),
        'active_games': GameRecord.query.filter(
            GameRecord.created_at >= month_start
        ).count(),
        'points_given': db.session.query(db.func.sum(PointRecord.points)).filter(
            PointRecord.created_at >= month_start
        ).scalar() or 0
    }
    
    return jsonify({
        'today': today_stats,
        'week': week_stats,
        'month': month_stats
    })

@admin_bp.route('/api/statistics/trends')
@login_required
@admin_required
def api_statistics_trends():
    from collections import defaultdict
    
    days = request.args.get('days', 7, type=int)
    end_date = date.today()
    start_date = end_date - timedelta(days=days-1)
    
    start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
    
    # 游戏趋势
    game_list = GameRecord.query.filter(GameRecord.created_at >= start_dt).all()
    game_map = defaultdict(int)
    for g in game_list:
        if g.created_at:
            d = g.created_at.date() if hasattr(g.created_at, 'date') else g.created_at
            game_map[str(d)] += 1
    game_dict = dict(game_map)
    
    # 用户增长趋势
    user_list = User.query.filter(User.created_at >= start_dt).all()
    user_map = defaultdict(int)
    for u in user_list:
        if u.created_at:
            d = u.created_at.date() if hasattr(u.created_at, 'date') else u.created_at
            user_map[str(d)] += 1
    user_dict = dict(user_map)
    
    game_trend = []
    user_trend = []
    current = start_date
    while current <= end_date:
        date_str = current.strftime('%Y-%m-%d')
        game_trend.append({
            'date': date_str,
            'count': game_dict.get(date_str, 0)
        })
        user_trend.append({
            'date': date_str,
            'count': user_dict.get(date_str, 0)
        })
        current += timedelta(days=1)
    
    return jsonify({
        'game_trend': game_trend,
        'user_trend': user_trend
    })
