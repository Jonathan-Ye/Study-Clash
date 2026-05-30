from datetime import datetime, date, timedelta, timezone
from app import db
from app.models import User, Leaderboard, GameRecord, DailyStats, PointRecord
from sqlalchemy import func, desc, case, text
from sqlalchemy.orm import outerjoin

class LeaderboardCache:
    _cache = {}
    _cache_timeout = 300
    
    @classmethod
    def get_cache(cls, key):
        if key in cls._cache:
            data, timestamp = cls._cache[key]
            if datetime.now(timezone.utc) - timestamp < timedelta(seconds=cls._cache_timeout):
                return data
            del cls._cache[key]
        return None
    
    @classmethod
    def set_cache(cls, key, data):
        cls._cache[key] = (data, datetime.now(timezone.utc))
    
    @classmethod
    def clear_cache(cls):
        cls._cache.clear()
    
    @classmethod
    def clear_pattern(cls, pattern):
        keys_to_delete = [k for k in cls._cache if pattern in k]
        for key in keys_to_delete:
            del cls._cache[key]


def _get_period_start(period):
    today = date.today()
    if period == 'daily':
        return datetime(today.year, today.month, today.day)
    elif period == 'weekly':
        monday = today - timedelta(days=today.weekday())
        return datetime(monday.year, monday.month, monday.day)
    elif period == 'monthly':
        return datetime(today.year, today.month, 1)
    else:
        return None


def _build_score_subquery(category, period_start, subject_id=None, game_type=None):
    if category == 'total_points':
        if period_start is None:
            q = db.session.query(
                User.id.label('user_id'),
                User.total_points.label('score')
            ).filter(User.is_active == True, User.show_in_leaderboard == True)
            return q.subquery('scores')
        else:
            q = db.session.query(
                PointRecord.user_id.label('user_id'),
                func.coalesce(func.sum(PointRecord.points), 0).label('score')
            ).filter(PointRecord.created_at >= period_start)\
             .group_by(PointRecord.user_id)
            return q.subquery('scores')
    
    elif category == 'correct_rate':
        base_q = db.session.query(
            DailyStats.user_id.label('user_id'),
            func.coalesce(func.sum(DailyStats.questions_answered), 0).label('total_q'),
            func.coalesce(func.sum(DailyStats.correct_count), 0).label('correct_q')
        ).group_by(DailyStats.user_id)
        
        if period_start is not None:
            base_q = base_q.filter(DailyStats.created_at >= period_start)
        
        sq = base_q.subquery('stats_raw')
        
        q = db.session.query(
            sq.c.user_id,
            (case((sq.c.total_q > 0, func.cast(sq.c.correct_q * 100 / sq.c.total_q, db.Integer)), else_=0)).label('score')
        )
        return q.subquery('scores')
    
    elif category == 'games_won':
        base_q = db.session.query(
            GameRecord.user_id.label('user_id'),
            func.count().label('score')
        ).filter(GameRecord.rank == 1).group_by(GameRecord.user_id)
        
        if period_start is not None:
            base_q = base_q.filter(GameRecord.created_at >= period_start)
        
        return base_q.subquery('scores')
    
    elif category == 'streak_days':
        q = db.session.query(
            User.id.label('user_id'),
            User.streak_days.label('score')
        ).filter(User.is_active == True, User.show_in_leaderboard == True)
        return q.subquery('scores')
    
    elif category == 'subject_points' and subject_id:
        base_q = db.session.query(
            GameRecord.user_id.label('user_id'),
            func.coalesce(func.sum(GameRecord.points_earned), 0).label('score')
        ).filter(GameRecord.subject_id == subject_id).group_by(GameRecord.user_id)
        
        if period_start is not None:
            base_q = base_q.filter(GameRecord.created_at >= period_start)
        
        return base_q.subquery('scores')
    
    elif category == 'game_type_points' and game_type:
        base_q = db.session.query(
            GameRecord.user_id.label('user_id'),
            func.coalesce(func.sum(GameRecord.points_earned), 0).label('score')
        ).filter(GameRecord.game_type == game_type).group_by(GameRecord.user_id)
        
        if period_start is not None:
            base_q = base_q.filter(GameRecord.created_at >= period_start)
        
        return base_q.subquery('scores')
    
    elif category == 'study_time':
        base_q = db.session.query(
            DailyStats.user_id.label('user_id'),
            func.coalesce(func.sum(DailyStats.time_spent), 0).label('score')
        ).group_by(DailyStats.user_id)
        
        if period_start is not None:
            base_q = base_q.filter(DailyStats.created_at >= period_start)
        
        return base_q.subquery('scores')
    
    else:
        q = db.session.query(
            User.id.label('user_id'),
            User.total_points.label('score')
        ).filter(User.is_active == True, User.show_in_leaderboard == True)
        return q.subquery('scores')


def get_leaderboard_data(category='total_points', period='all_time', subject_id=None,
                        game_type=None, school=None, grade=None, class_name=None,
                        page=1, per_page=50):
    cache_key = f"lb_{category}_{period}_{subject_id}_{game_type}_{school}_{grade}_{class_name}_{page}_{per_page}"
    
    cached = LeaderboardCache.get_cache(cache_key)
    if cached:
        return cached
    
    period_start = _get_period_start(period)
    
    score_sq = _build_score_subquery(category, period_start, subject_id, game_type)
    
    base = db.session.query(
        User,
        func.coalesce(score_sq.c.score, 0).label('score')
    ).select_from(outerjoin(User, score_sq, User.id == score_sq.c.user_id))\
     .filter(User.is_active == True, User.show_in_leaderboard == True)
    
    if school:
        base = base.filter(User.school == school)
    if grade:
        base = base.filter(User.grade == grade)
    if class_name:
        base = base.filter(User.class_name == class_name)
    
    count_query = db.session.query(func.count()).select_from(base.subquery())
    total = count_query.scalar() or 0
    
    ordered_query = base.order_by(desc(text('score')), User.id)
    
    paginated = ordered_query.offset((page - 1) * per_page).limit(per_page).all()
    
    entries = []
    start_rank = (page - 1) * per_page + 1
    for i, row in enumerate(paginated):
        entries.append({
            'rank': start_rank + i,
            'user': row[0],
            'score': int(row[1]) if row[1] is not None else 0
        })
    
    pagination = FakePagination(entries, total, page, per_page)
    
    result = {
        'entries': entries,
        'pagination': pagination,
        'total': total
    }
    
    LeaderboardCache.set_cache(cache_key, result)
    return result


def get_my_rank(user_id, category='total_points', period='all_time', subject_id=None,
               game_type=None, school=None, grade=None, class_name=None):
    cache_key = f"myrank_{user_id}_{category}_{period}_{subject_id}_{game_type}_{school}_{grade}_{class_name}"
    
    cached = LeaderboardCache.get_cache(cache_key)
    if cached is not None:
        return cached
    
    period_start = _get_period_start(period)
    
    score_sq = _build_score_subquery(category, period_start, subject_id, game_type)
    
    my_row = db.session.query(
        func.coalesce(score_sq.c.score, 0).label('my_score')
    ).select_from(outerjoin(User, score_sq, User.id == score_sq.c.user_id))\
     .filter(User.id == user_id, User.is_active == True).first()
    
    my_score = int(my_row.my_score) if my_row and my_row.my_score is not None else 0
    
    rank_base = db.session.query(
        User.id,
        func.coalesce(score_sq.c.score, 0).label('s')
    ).select_from(outerjoin(User, score_sq, User.id == score_sq.c.user_id))\
     .filter(User.is_active == True)
    
    if school:
        rank_base = rank_base.filter(User.school == school)
    if grade:
        rank_base = rank_base.filter(User.grade == grade)
    if class_name:
        rank_base = rank_base.filter(User.class_name == class_name)
    
    rank_sq = rank_base.subquery()
    higher_count = db.session.query(func.count()).select_from(rank_sq)\
        .filter(rank_sq.c.s > my_score).scalar() or 0
    
    rank = higher_count + 1
    LeaderboardCache.set_cache(cache_key, rank)
    return rank


class FakePagination:
    def __init__(self, items, total, page, per_page):
        self.items = items
        self.total = total
        self.page = page
        self.per_page = per_page
        self.pages = max(1, (total + per_page - 1) // per_page)
    
    @property
    def has_prev(self):
        return self.page > 1
    
    @property
    def has_next(self):
        return self.page < self.pages
    
    @property
    def prev_num(self):
        return self.page - 1
    
    @property
    def next_num(self):
        return self.page + 1
    
    def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num


def invalidate_leaderboard_cache():
    LeaderboardCache.clear_pattern('lb_')
    LeaderboardCache.clear_pattern('myrank_')


def calculate_user_stats(user_id):
    total_questions = db.session.query(func.sum(DailyStats.questions_answered))\
        .filter(DailyStats.user_id == user_id).scalar() or 0
    total_correct = db.session.query(func.sum(DailyStats.correct_count))\
        .filter(DailyStats.user_id == user_id).scalar() or 0
    total_wrong = db.session.query(func.sum(DailyStats.wrong_count))\
        .filter(DailyStats.user_id == user_id).scalar() or 0
    total_games = db.session.query(func.sum(DailyStats.games_played))\
        .filter(DailyStats.user_id == user_id).scalar() or 0
    games_won = db.session.query(func.sum(DailyStats.games_won))\
        .filter(DailyStats.user_id == user_id).scalar() or 0
    study_time = db.session.query(func.sum(DailyStats.time_spent))\
        .filter(DailyStats.user_id == user_id).scalar() or 0
    
    accuracy = round(total_correct / total_questions * 100, 1) if total_questions > 0 else 0
    
    return {
        'total_questions': total_questions,
        'total_correct': total_correct,
        'total_wrong': total_wrong,
        'total_games': total_games,
        'games_won': games_won,
        'study_time': study_time,
        'accuracy': accuracy
    }


def get_subject_points(user_id, subject_id):
    return db.session.query(func.sum(GameRecord.points_earned))\
        .filter(GameRecord.user_id == user_id, GameRecord.subject_id == subject_id).scalar() or 0


def get_game_type_points(user_id, game_type):
    return db.session.query(func.sum(GameRecord.points_earned))\
        .filter(GameRecord.user_id == user_id, GameRecord.game_type == game_type).scalar() or 0


def update_leaderboard(period='all_time', category='total_points', subject_id=None, 
                      game_type=None, school=None, grade=None, class_name=None):
    invalidate_leaderboard_cache()
    
    users_query = User.query.filter_by(is_active=True)
    
    if school:
        users_query = users_query.filter(User.school == school)
    if grade:
        users_query = users_query.filter(User.grade == grade)
    if class_name:
        users_query = users_query.filter(User.class_name == class_name)
    
    all_users = users_query.all()
    period_start = _get_period_start(period)
    score_sq = _build_score_subquery(category, period_start, subject_id, game_type)
    
    score_map = {}
    for row in db.session.query(score_sq.c.user_id, score_sq.c.score).all():
        score_map[row[0]] = int(row[1]) if row[1] is not None else 0
    
    leaderboard_entries = []
    for user in all_users:
        score = score_map.get(user.id, 0) if period_start is not None or category != 'total_points' else user.total_points
        
        leaderboard_entries.append({
            'user_id': user.id,
            'score': score,
            'user': user
        })
    
    leaderboard_entries.sort(key=lambda x: x['score'], reverse=True)
    
    for idx, entry in enumerate(leaderboard_entries):
        existing = Leaderboard.query.filter_by(
            user_id=entry['user_id'],
            period=period,
            category=category,
            subject_id=subject_id,
            game_type=game_type,
            school=school,
            grade=grade,
            class_name=class_name
        ).first()
        
        if existing:
            existing.score = entry['score']
            existing.rank = idx + 1
        else:
            new_entry = Leaderboard(
                user_id=entry['user_id'],
                period=period,
                category=category,
                subject_id=subject_id,
                game_type=game_type,
                school=school,
                grade=grade,
                class_name=class_name,
                score=entry['score'],
                rank=idx + 1
            )
            db.session.add(new_entry)
    
    db.session.commit()
    
    return leaderboard_entries


def get_available_schools():
    return db.session.query(User.school).filter(User.school.isnot(None), User.school != '').distinct().all()


def get_available_grades():
    return db.session.query(User.grade).filter(User.grade.isnot(None), User.grade != '').distinct().all()


def get_available_classes():
    return db.session.query(User.class_name).filter(User.class_name.isnot(None), User.class_name != '').distinct().all()
