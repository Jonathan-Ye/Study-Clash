from datetime import date, datetime, timedelta, timezone
from flask import render_template, jsonify, request
from flask_login import login_required
from app import db
from app.models import User, Question, Subject, GameRecord, PointRecord, DailyStats
from app.models.announcement import Announcement
from app.routes.admin import admin_bp, admin_required


def get_date_range_filter(column, target_date):
    """生成日期范围查询（PostgreSQL）"""
    next_date = target_date + timedelta(days=1)
    start_dt = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    end_dt = datetime(next_date.year, next_date.month, next_date.day, tzinfo=timezone.utc)
    return (column >= start_dt) & (column < end_dt)


@admin_bp.route('/')
@login_required
@admin_required
def index():
    today = date.today()

    stats = {
        'total_users': User.query.count(),
        'active_users': User.query.filter_by(is_active=True).count(),
        'new_users_today': User.query.filter(get_date_range_filter(User.created_at, today)).count(),
        'total_questions': Question.query.count(),
        'active_questions': Question.query.filter_by(is_active=True).count(),
        'total_games': GameRecord.query.count(),
        'games_today': GameRecord.query.filter(get_date_range_filter(GameRecord.created_at, today)).count(),
        'total_points_given': db.session.query(db.func.sum(PointRecord.points)).scalar() or 0,
        'points_today': db.session.query(db.func.sum(PointRecord.points)).filter(
            get_date_range_filter(PointRecord.created_at, today)
        ).scalar() or 0,
        'active_announcements': Announcement.query.filter(
            Announcement.status.in_(['published', 'pending']),
            db.or_(Announcement.expire_at.is_(None), Announcement.expire_at > datetime.now(timezone.utc))
        ).count()
    }

    # 紧急公告提醒
    urgent_announcements = Announcement.query.filter(
        Announcement.priority == 'urgent',
        Announcement.status.in_(['published', 'pending']),
        db.or_(Announcement.expire_at.is_(None), Announcement.expire_at > datetime.now(timezone.utc))
    ).order_by(Announcement.created_at.desc()).limit(3).all()

    return render_template('admin/index.html',
                          stats=stats,
                          urgent_announcements=urgent_announcements)


@admin_bp.route('/api/dashboard/trends')
@login_required
@admin_required
def api_dashboard_trends():
    """仪表盘趋势数据API"""
    days = request.args.get('days', 7, type=int)
    if days not in (7, 30):
        days = 7

    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    # 用户增长趋势
    user_growth = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        count = User.query.filter(get_date_range_filter(User.created_at, d)).count()
        user_growth.append({'date': d.isoformat(), 'count': count})

    # 游戏活跃趋势
    game_active = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        count = GameRecord.query.filter(get_date_range_filter(GameRecord.created_at, d)).count()
        game_active.append({'date': d.isoformat(), 'count': count})

    # 积分发放趋势
    points_given = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        total = db.session.query(db.func.sum(PointRecord.points)).filter(
            get_date_range_filter(PointRecord.created_at, d)
        ).scalar() or 0
        points_given.append({'date': d.isoformat(), 'count': int(total)})

    return jsonify({
        'user_growth': user_growth,
        'game_active': game_active,
        'points_given': points_given
    })


@admin_bp.route('/api/dashboard/distribution')
@login_required
@admin_required
def api_dashboard_distribution():
    """仪表盘分布数据API"""
    # 按学科分布
    by_subject = db.session.query(
        Subject.name, db.func.count(Question.id)
    ).join(Question, Subject.id == Question.subject_id, isouter=True).group_by(
        Subject.id, Subject.name
    ).all()

    # 按难度分布
    by_difficulty = db.session.query(
        Question.difficulty, db.func.count(Question.id)
    ).group_by(Question.difficulty).all()

    # 按题型分布
    by_type = db.session.query(
        Question.question_type, db.func.count(Question.id)
    ).group_by(Question.question_type).all()

    # 按启用状态分布
    by_status = db.session.query(
        Question.is_active, db.func.count(Question.id)
    ).group_by(Question.is_active).all()

    difficulty_map = {1: '简单', 2: '中等', 3: '困难', 4: '极难'}
    type_map = {'single': '单选', 'multiple': '多选', 'judge': '判断', 'fill': '填空'}

    return jsonify({
        'by_subject': [{'name': n or '未分类', 'count': c} for n, c in by_subject],
        'by_difficulty': [{'name': difficulty_map.get(d, str(d)), 'count': c} for d, c in by_difficulty],
        'by_type': [{'name': type_map.get(t, t), 'count': c} for t, c in by_type],
        'by_status': [{'name': '启用' if a else '禁用', 'count': c} for a, c in by_status]
    })
