from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from datetime import date, timedelta
from sqlalchemy import func

from app import db
from app.models import User, Subject, GameRecord, PointRecord, DailyStats, RankTier, TierPromotionHistory
from app.utils.leaderboard_service import (
    get_leaderboard_data,
    get_my_rank,
    get_available_schools,
    get_available_grades,
    get_available_classes
)

# 创建 Blueprint
points_bp = Blueprint('points', __name__)


@points_bp.route('/leaderboard')
@login_required
def leaderboard():
    period = request.args.get('period', 'all_time')
    category = request.args.get('category', 'total_points')
    subject_id = request.args.get('subject_id', type=int)
    game_type = request.args.get('game_type')
    school = request.args.get('school')
    grade = request.args.get('grade')
    class_name = request.args.get('class_name')
    page = request.args.get('page', 1, type=int)
    
    subjects = Subject.query.filter_by(is_active=True).all()
    user_major = getattr(current_user, 'major', None)
    filtered_subjects = [s for s in subjects if s.is_applicable_for_major(user_major)]
    schools = [s[0] for s in get_available_schools()]
    grades = [g[0] for g in get_available_grades()]
    classes = [c[0] for c in get_available_classes()]
    
    result = get_leaderboard_data(
        category=category, period=period, subject_id=subject_id,
        game_type=game_type, school=school, grade=grade, 
        class_name=class_name, page=page, per_page=50
    )
    
    entries = result['entries']
    pagination = result['pagination']
    
    my_rank = get_my_rank(
        user_id=current_user.id, category=category, period=period,
        subject_id=subject_id, game_type=game_type, school=school,
        grade=grade, class_name=class_name
    )
    
    from app.utils.rank_service import RankService
    
    all_tiers = RankService.get_all_tiers_ordered()
    
    # 预先按段位名称分组（避免在模板中进行复杂操作）
    tier_groups = {}
    for tier in all_tiers:
        if tier.tier_name not in tier_groups:
            tier_groups[tier.tier_name] = []
        tier_groups[tier.tier_name].append(tier)
    
    return render_template('points/leaderboard.html', 
                          entries=entries, 
                          pagination=pagination,
                          period=period,
                          category=category,
                          subject_id=subject_id,
                          game_type=game_type,
                          school=school,
                          grade=grade,
                          class_name=class_name,
                          subjects=filtered_subjects,
                          schools=schools,
                          grades=grades,
                          classes=classes,
                          my_rank=my_rank,
                          all_tiers=all_tiers,
                          tier_groups=tier_groups)

@points_bp.route('/my-points')
@login_required
def my_points():
    page = request.args.get('page', 1, type=int)
    
    records = PointRecord.query.filter_by(user_id=current_user.id)\
        .order_by(PointRecord.created_at.desc())\
        .paginate(page=page, per_page=20)
    
    user_rank = current_user.get_rank()
    
    return render_template('points/my_points.html', records=records, user_rank=user_rank)

@points_bp.route('/statistics')
@login_required
def statistics():
    return render_template('points/statistics.html')

@points_bp.route('/api/statistics/overview')
@login_required
def api_overview():
    cache_key = f'overview_{current_user.id}'
    cached = _get_cached_stats(cache_key)
    if cached:
        return jsonify(cached)
    
    stats = db.session.query(
        func.count(DailyStats.id).label('total_days'),
        func.sum(DailyStats.questions_answered).label('questions'),
        func.sum(DailyStats.correct_count).label('correct'),
        func.sum(DailyStats.wrong_count).label('wrong'),
        func.sum(DailyStats.games_played).label('games'),
        func.sum(DailyStats.games_won).label('games_won'),
        func.sum(DailyStats.time_spent).label('time_spent'),
        func.sum(DailyStats.points_earned).label('points_earned')
    ).filter(DailyStats.user_id == current_user.id).first()
    
    total_correct = stats.correct or 0
    total_wrong = stats.wrong or 0
    total_games = stats.games or 0
    total_games_won = stats.games_won or 0
    total_time = stats.time_spent or 0
    
    accuracy = round(total_correct / (total_correct + total_wrong) * 100, 1) if (total_correct + total_wrong) > 0 else 0
    win_rate = round(total_games_won / total_games * 100, 1) if total_games > 0 else 0
    
    result = {
        'total_points': current_user.total_points,
        'tier': {
            'tier_name': current_user.current_tier.tier_name if current_user.current_tier else None,
            'sub_tier': current_user.current_tier.sub_tier if current_user.current_tier else None,
            'display_name': current_user.current_tier.display_name if current_user.current_tier else None,
            'icon': current_user.current_tier.icon if current_user.current_tier else None,
            'color': current_user.current_tier.color if current_user.current_tier else None
        },
        'peak_tier': {
            'display_name': current_user.peak_tier.display_name if current_user.peak_tier else None,
            'icon': current_user.peak_tier.icon if current_user.peak_tier else None,
            'color': current_user.peak_tier.color if current_user.peak_tier else None
        } if current_user.peak_tier else None,
        'level': current_user.level,
        'streak_days': current_user.streak_days,
        'total_questions': int(stats.questions or 0),
        'correct_rate': accuracy,
        'total_games': int(total_games),
        'games_won': int(total_games_won),
        'win_rate': win_rate,
        'total_time': int(total_time),
        'total_time_hours': round(total_time / 3600, 1)
    }
    _set_cached_stats(cache_key, result)
    return jsonify(result)

@points_bp.route('/api/statistics/daily')
@login_required
def api_daily_stats():
    days = request.args.get('days', 7, type=int)
    cache_key = f'daily_{current_user.id}_{days}'
    cached = _get_cached_stats(cache_key)
    if cached:
        return jsonify(cached)
    end_date = date.today()
    start_date = end_date - timedelta(days=days-1)
    
    stats = DailyStats.query.filter(
        DailyStats.user_id == current_user.id,
        DailyStats.date >= start_date,
        DailyStats.date <= end_date
    ).order_by(DailyStats.date).all()
    
    stats_dict = {s.date: s for s in stats}
    
    result = []
    current = start_date
    while current <= end_date:
        stat = stats_dict.get(current)
        result.append({
            'date': current.strftime('%m-%d'),
            'questions': stat.questions_answered if stat else 0,
            'correct': stat.correct_count if stat else 0,
            'wrong': stat.wrong_count if stat else 0,
            'accuracy': stat.accuracy if stat else 0,
            'points': stat.points_earned if stat else 0,
            'time': stat.time_spent if stat else 0,
            'games': stat.games_played if stat else 0
        })
        current += timedelta(1)
    
    _set_cached_stats(cache_key, result)
    return jsonify(result)

@points_bp.route('/api/statistics/subjects')
@login_required
def api_subject_stats():
    cache_key = f'subjects_{current_user.id}'
    cached = _get_cached_stats(cache_key)
    if cached:
        return jsonify(cached)
    
    subject_stats = db.session.query(
        Subject.name,
        func.count(GameRecord.id).label('games'),
        func.sum(GameRecord.correct_count).label('correct'),
        func.sum(GameRecord.wrong_count).label('wrong'),
        func.sum(GameRecord.points_earned).label('points')
    ).join(GameRecord, Subject.id == GameRecord.subject_id)\
     .filter(GameRecord.user_id == current_user.id)\
     .group_by(Subject.id)\
     .all()
    
    result = [{
        'subject': stat.name,
        'games': stat.games,
        'correct': stat.correct or 0,
        'wrong': stat.wrong or 0,
        'points': stat.points or 0
    } for stat in subject_stats]
    
    _set_cached_stats(cache_key, result)
    return jsonify(result)

@points_bp.route('/api/statistics/game-types')
@login_required
def api_game_type_stats():
    cache_key = f'gametypes_{current_user.id}'
    cached = _get_cached_stats(cache_key)
    if cached:
        return jsonify(cached)
    
    game_type_stats = db.session.query(
        GameRecord.game_type,
        func.count(GameRecord.id).label('games'),
        func.sum(GameRecord.correct_count).label('correct'),
        func.sum(GameRecord.wrong_count).label('wrong'),
        func.sum(GameRecord.points_earned).label('points'),
        func.sum(GameRecord.total_time).label('time')
    ).filter(GameRecord.user_id == current_user.id)\
     .group_by(GameRecord.game_type)\
     .all()
    
    result = [{
        'type': stat.game_type,
        'games': stat.games,
        'correct': stat.correct or 0,
        'wrong': stat.wrong or 0,
        'points': stat.points or 0,
        'time': stat.time or 0
    } for stat in game_type_stats]
    
    _set_cached_stats(cache_key, result)
    return jsonify(result)

@points_bp.route('/api/rank-history')
@login_required
def api_rank_history():
    days = request.args.get('days', 30, type=int)
    end_date = date.today()
    start_date = end_date - timedelta(days=days-1)
    
    from app.models import RankHistory
    history = RankHistory.query.filter(
        RankHistory.user_id == current_user.id,
        RankHistory.recorded_at >= start_date,
        RankHistory.recorded_at <= end_date
    ).order_by(RankHistory.recorded_at.asc()).all()
    
    result = [{
        'date': h.recorded_at.strftime('%Y-%m-%d'),
        'rank': h.rank,
        'points': h.score
    } for h in history]
    
    return jsonify(result)

@points_bp.route('/api/rank-info')
@login_required
def api_rank_info():
    """获取用户当前排名信息"""
    current_rank = current_user.get_rank()
    
    return jsonify({
        'current_rank': current_rank,
        'total_points': current_user.total_points or 0
    })

@points_bp.route('/api/rank/my-tier')
@login_required
def api_my_tier():
    """获取当前用户的段位信息"""
    from app.utils.rank_service import RankService
    
    tier_data = RankService.get_user_current_tier(current_user)
    progress_data = RankService.get_tier_progress(current_user)
    
    # 获取段位升级历史（最近10条）
    history = TierPromotionHistory.query.filter_by(user_id=current_user.id)\
        .order_by(TierPromotionHistory.changed_at.desc()).limit(10).all()
    
    result = {
        'current': {
            'tier_id': tier_data.id if tier_data else None,
            'tier_name': tier_data.tier_name if tier_data else None,
            'sub_tier': tier_data.sub_tier if tier_data else None,
            'display_name': tier_data.display_name if tier_data else None,
            'icon': tier_data.icon if tier_data else None,
            'color': tier_data.color if tier_data else None,
            'tier_order': tier_data.tier_order if tier_data else None
        },
        'peak': {
            'display_name': current_user.peak_tier.display_name if current_user.peak_tier else None,
            'icon': current_user.peak_tier.icon if current_user.peak_tier else None,
            'color': current_user.peak_tier.color if current_user.peak_tier else None
        } if current_user.peak_tier else None,
        'progress': progress_data,
        'stats': {
            'total_promotions': len(history),
            'last_promoted_at': history[0].changed_at.strftime('%Y-%m-%d %H:%M') if history else None
        }
    }
    
    return jsonify(result)

@points_bp.route('/api/rank/tier-history')
@login_required
def api_tier_history():
    """获取用户段位变更历史"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    history = TierPromotionHistory.query.filter_by(user_id=current_user.id)\
        .order_by(TierPromotionHistory.changed_at.desc())\
        .paginate(page=page, per_page=per_page)
    
    result = {
        'total': history.total,
        'page': page,
        'per_page': per_page,
        'history': [{
            'id': h.id,
            'from_tier': h.from_tier.display_name if h.from_tier else None,
            'to_tier': h.to_tier.display_name if h.to_tier else None,
            'points_at': h.points_at_change,
            'promoted_at': h.changed_at.strftime('%Y-%m-%d %H:%M')
        } for h in history.items]
    }
    
    return jsonify(result)

@points_bp.route('/api/rank/tier-list')
def api_tier_list():
    """获取所有段位列表"""
    from app.utils.rank_service import RankService
    
    tiers = RankService.get_all_tiers_ordered()
    
    return jsonify({
        'tiers': [t.to_dict() for t in tiers],
        'total': len(tiers)
    })

@points_bp.route('/api/rank/distribution')
def api_distribution():
    """获取全站段位分布"""
    from app.utils.rank_service import RankService
    
    distribution = RankService.get_tier_distribution()
    total_users = sum(d['count'] for d in distribution)
    
    return jsonify({
        'distribution': distribution,
        'total_users': total_users
    })

# 缓存相关
_stats_cache = {}
_cache_timeout = 300

def _get_cached_stats(key):
    import time
    if key in _stats_cache:
        data, timestamp = _stats_cache[key]
        if time.time() - timestamp < _cache_timeout:
            return data
    return None

def _set_cached_stats(key, data):
    import time
    _stats_cache[key] = (data, time.time())
