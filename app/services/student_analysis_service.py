from datetime import datetime, timedelta, date
from app import db
from app.models import (User, UserAnswer, GameRecord, PointRecord, 
                        WrongQuestion, DailyStats, DictionaryItem, 
                        RankTier, Subject, Chapter, Question)


def _get_time_start(time_range):
    """根据时间范围字符串计算起始日期"""
    today = date.today()
    if time_range == '7d':
        return today - timedelta(days=7)
    elif time_range == '30d':
        return today - timedelta(days=30)
    elif time_range == '90d':
        return today - timedelta(days=90)
    return None  # all


def get_category_options(category):
    """获取班级或专业的选项列表"""
    code = 'class_name' if category == 'class_name' else 'major'
    items = DictionaryItem.get_options(code)
    return [item.value for item in items]


def get_category_overview(category, time_range='all', sort_by='student_count'):
    """获取分类概览聚合数据"""
    start_date = _get_time_start(time_range)
    
    # 获取所有选项（包括没有学生的分类）
    options = get_category_options(category)
    
    # 查询非管理员活跃学生，按分类字段分组
    category_field = User.class_name if category == 'class_name' else User.major
    users_query = User.query.filter(
        User.is_admin == False,
        User.is_active == True
    )
    
    # 获取所有学生
    all_students = users_query.all()
    
    # 按分类分组
    category_students = {}
    for student in all_students:
        cat_value = getattr(student, category, None)
        if cat_value:
            if cat_value not in category_students:
                category_students[cat_value] = []
            category_students[cat_value].append(student)
    
    # 获取用户ID列表
    all_user_ids = [s.id for s in all_students]
    
    # 批量查询答题正确率
    answer_stats = {}
    if all_user_ids:
        answer_query = db.session.query(
            UserAnswer.user_id,
            db.func.count(UserAnswer.id).label('total'),
            db.func.sum(db.case((UserAnswer.is_correct == True, 1), else_=0)).label('correct')
        )
        if start_date:
            answer_query = answer_query.filter(UserAnswer.created_at >= start_date)
        answer_results = answer_query.group_by(UserAnswer.user_id).all()
        answer_stats = {r.user_id: {'total': r.total, 'correct': r.correct} for r in answer_results}
    
    # 批量查询游戏场次
    game_stats = {}
    if all_user_ids:
        game_query = db.session.query(
            GameRecord.user_id,
            db.func.count(GameRecord.id).label('count')
        )
        if start_date:
            game_query = game_query.filter(GameRecord.created_at >= start_date)
        game_results = game_query.group_by(GameRecord.user_id).all()
        game_stats = {r.user_id: r.count for r in game_results}
    
    # 批量查询活跃学生
    active_user_ids = set()
    if all_user_ids and start_date:
        active_results = DailyStats.query.filter(
            DailyStats.date >= start_date,
            DailyStats.user_id.in_(all_user_ids)
        ).with_entities(DailyStats.user_id).distinct().all()
        active_user_ids = {r.user_id for r in active_results}
    elif all_user_ids:
        # 全部时间范围，有daily_stats记录即为活跃
        active_results = DailyStats.query.filter(
            DailyStats.user_id.in_(all_user_ids)
        ).with_entities(DailyStats.user_id).distinct().all()
        active_user_ids = {r.user_id for r in active_results}
    
    # 组装概览数据
    categories_data = []
    for option_value in options:
        students = category_students.get(option_value, [])
        student_count = len(students)
        
        if student_count == 0:
            categories_data.append({
                'name': option_value,
                'student_count': 0,
                'avg_accuracy': None,
                'avg_points': 0,
                'avg_games': 0,
                'active_count': 0,
                'active_ratio': 0
            })
            continue
        
        # 计算平均积分
        avg_points = round(sum(s.total_points or 0 for s in students) / student_count)
        
        # 计算平均正确率
        accuracies = []
        for s in students:
            stat = answer_stats.get(s.id)
            if stat and stat['total'] > 0:
                accuracies.append(round(stat['correct'] / stat['total'] * 100, 1))
        avg_accuracy = round(sum(accuracies) / len(accuracies), 1) if accuracies else None
        
        # 计算平均游戏场次
        game_counts = [game_stats.get(s.id, 0) for s in students]
        avg_games = round(sum(game_counts) / student_count, 1)
        
        # 计算活跃学生数
        active_count = len([s for s in students if s.id in active_user_ids])
        active_ratio = round(active_count / student_count * 100, 1) if student_count > 0 else 0
        
        categories_data.append({
            'name': option_value,
            'student_count': student_count,
            'avg_accuracy': avg_accuracy,
            'avg_points': avg_points,
            'avg_games': avg_games,
            'active_count': active_count,
            'active_ratio': active_ratio
        })
    
    # 也加入有学生但不在字典选项中的分类
    for cat_value, students in category_students.items():
        if cat_value not in options:
            student_count = len(students)
            avg_points = round(sum(s.total_points or 0 for s in students) / student_count)
            accuracies = []
            for s in students:
                stat = answer_stats.get(s.id)
                if stat and stat['total'] > 0:
                    accuracies.append(round(stat['correct'] / stat['total'] * 100, 1))
            avg_accuracy = round(sum(accuracies) / len(accuracies), 1) if accuracies else None
            game_counts = [game_stats.get(s.id, 0) for s in students]
            avg_games = round(sum(game_counts) / student_count, 1)
            active_count = len([s for s in students if s.id in active_user_ids])
            active_ratio = round(active_count / student_count * 100, 1) if student_count > 0 else 0
            categories_data.append({
                'name': cat_value,
                'student_count': student_count,
                'avg_accuracy': avg_accuracy,
                'avg_points': avg_points,
                'avg_games': avg_games,
                'active_count': active_count,
                'active_ratio': active_ratio
            })
    
    # 排序
    sort_key_map = {
        'student_count': 'student_count',
        'avg_accuracy': 'avg_accuracy',
        'avg_points': 'avg_points'
    }
    sort_key = sort_key_map.get(sort_by, 'student_count')
    categories_data.sort(
        key=lambda x: x[sort_key] if x[sort_key] is not None else -1, 
        reverse=True
    )
    
    return {'categories': categories_data}


def get_category_students(category, value, sort_by='points', page=1, per_page=20, search=None, time_range='all'):
    """获取分类下学生列表及统计"""
    start_date = _get_time_start(time_range)
    
    # 查询学生
    query = User.query.filter(
        User.is_admin == False,
        User.is_active == True
    )
    
    if category == 'class_name':
        query = query.filter(User.class_name == value)
    else:
        query = query.filter(User.major == value)
    
    # 搜索
    if search:
        search_filter = db.or_(
            User.real_name.contains(search),
            User.student_id.contains(search),
            User.username.contains(search)
        )
        query = query.filter(search_filter)
    
    # 先获取总数
    total = query.count()
    
    # 获取学生列表
    students = query.all()
    student_ids = [s.id for s in students]
    
    # 批量查询答题正确率
    answer_stats = {}
    if student_ids:
        answer_query = db.session.query(
            UserAnswer.user_id,
            db.func.count(UserAnswer.id).label('total'),
            db.func.sum(db.case((UserAnswer.is_correct == True, 1), else_=0)).label('correct')
        ).filter(UserAnswer.user_id.in_(student_ids))
        if start_date:
            answer_query = answer_query.filter(UserAnswer.created_at >= start_date)
        answer_results = answer_query.group_by(UserAnswer.user_id).all()
        answer_stats = {r.user_id: {'total': r.total, 'correct': r.correct} for r in answer_results}
    
    # 批量查询游戏场次
    game_stats = {}
    if student_ids:
        game_query = db.session.query(
            GameRecord.user_id,
            db.func.count(GameRecord.id).label('count')
        ).filter(GameRecord.user_id.in_(student_ids))
        if start_date:
            game_query = game_query.filter(GameRecord.created_at >= start_date)
        game_results = game_query.group_by(GameRecord.user_id).all()
        game_stats = {r.user_id: r.count for r in game_results}
    
    # 组装学生数据
    students_data = []
    for student in students:
        stat = answer_stats.get(student.id)
        if stat and stat['total'] > 0:
            accuracy = round(stat['correct'] / stat['total'] * 100, 1)
        else:
            accuracy = None
        
        games_played = game_stats.get(student.id, 0)
        
        tier_name = '未定级'
        tier_icon = ''
        if student.current_tier:
            tier_name = student.current_tier.display_name
            tier_icon = student.current_tier.icon or ''
        
        last_active = ''
        if student.last_login:
            last_active = student.last_login.strftime('%Y-%m-%d')
        
        students_data.append({
            'id': student.id,
            'name': student.real_name or student.nickname or student.username,
            'student_id': student.student_id or '--',
            'total_points': student.total_points,
            'accuracy': accuracy,
            'games_played': games_played,
            'tier_name': tier_name,
            'tier_icon': tier_icon,
            'last_active': last_active
        })
    
    # 排序
    sort_key_map = {
        'points': 'total_points',
        'accuracy': 'accuracy',
        'games': 'games_played',
        'last_active': 'last_active'
    }
    sort_key = sort_key_map.get(sort_by, 'total_points')
    reverse = sort_by != 'last_active'  # 最近活跃时间升序更合理
    students_data.sort(
        key=lambda x: x[sort_key] if x[sort_key] is not None else (-1 if reverse else ''),
        reverse=reverse
    )
    
    # 分页
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated = students_data[start_idx:end_idx]
    
    return {
        'students': paginated,
        'total': total,
        'page': page,
        'per_page': per_page
    }


def get_student_profile(user_id, time_range='30d'):
    """获取单个学生画像全维度数据"""
    start_date = _get_time_start(time_range)
    student = User.query.get(user_id)
    if not student:
        return None
    
    # 基础信息
    basic_info = {
        'id': student.id,
        'name': student.real_name or student.nickname or student.username,
        'student_id': student.student_id or '--',
        'class_name': student.class_name or '--',
        'major': student.major or '--',
        'school': student.school or '--',
        'registered_at': student.created_at.strftime('%Y-%m-%d') if student.created_at else '--',
        'last_login': student.last_login.strftime('%Y-%m-%d %H:%M') if student.last_login else '--'
    }
    
    # 答题分析
    answer_query = db.session.query(
        UserAnswer.user_id,
        db.func.count(UserAnswer.id).label('total'),
        db.func.sum(db.case((UserAnswer.is_correct == True, 1), else_=0)).label('correct')
    ).filter(UserAnswer.user_id == user_id)
    if start_date:
        answer_query = answer_query.filter(UserAnswer.created_at >= start_date)
    answer_result = answer_query.first()
    
    total_answers = answer_result.total if answer_result else 0
    correct_answers = answer_result.correct if answer_result else 0
    wrong_answers = total_answers - correct_answers
    accuracy = round(correct_answers / total_answers * 100, 1) if total_answers > 0 else None
    
    # 按学科统计正确率
    by_subject = []
    subject_query = db.session.query(
        Subject.name,
        db.func.count(UserAnswer.id).label('total'),
        db.func.sum(db.case((UserAnswer.is_correct == True, 1), else_=0)).label('correct')
    ).join(
        Question, Question.id == UserAnswer.question_id
    ).join(
        Subject, Subject.id == Question.subject_id
    ).filter(UserAnswer.user_id == user_id)
    if start_date:
        subject_query = subject_query.filter(UserAnswer.created_at >= start_date)
    subject_results = subject_query.group_by(Subject.id).all()
    
    for r in subject_results:
        sub_acc = round(r.correct / r.total * 100, 1) if r.total > 0 else 0
        by_subject.append({
            'subject': r.name,
            'accuracy': sub_acc,
            'total': r.total
        })
    
    answer_stats = {
        'total': total_answers,
        'correct': correct_answers,
        'wrong': wrong_answers,
        'accuracy': accuracy,
        'by_subject': by_subject
    }
    
    # 错题分析
    wrong_total = WrongQuestion.query.filter_by(user_id=user_id).count()
    wrong_mastered = WrongQuestion.query.filter_by(user_id=user_id, is_mastered=True).count()
    wrong_not_mastered = wrong_total - wrong_mastered
    
    # 薄弱知识点
    weak_points_raw = WrongQuestion.get_weak_points(user_id, limit=5)
    weak_points = []
    for wp in weak_points_raw:
        weak_points.append({
            'chapter': wp.name,
            'wrong_count': wp.wrong_count,
            'subject': wp.subject_name
        })
    
    wrong_question_stats = {
        'total': wrong_total,
        'mastered': wrong_mastered,
        'not_mastered': wrong_not_mastered,
        'weak_points': weak_points
    }
    
    # 游戏表现
    game_query = GameRecord.query.filter_by(user_id=user_id)
    if start_date:
        game_query = game_query.filter(GameRecord.created_at >= start_date)
    game_total = game_query.count()
    game_won = game_query.filter(GameRecord.rank == 1).count()
    win_rate = round(game_won / game_total * 100, 1) if game_total > 0 else None
    
    # 按游戏类型分布
    game_type_query = db.session.query(
        GameRecord.game_type,
        db.func.count(GameRecord.id).label('count')
    ).filter(GameRecord.user_id == user_id)
    if start_date:
        game_type_query = game_type_query.filter(GameRecord.created_at >= start_date)
    game_type_results = game_type_query.group_by(GameRecord.game_type).all()
    
    game_type_labels = {'single': '单人挑战', 'battle': '双人对战', 'four': '四人挑战'}
    by_type = []
    for r in game_type_results:
        by_type.append({
            'type': r.game_type,
            'count': r.count,
            'label': game_type_labels.get(r.game_type, r.game_type)
        })
    
    game_stats = {
        'total': game_total,
        'won': game_won,
        'win_rate': win_rate,
        'by_type': by_type
    }
    
    # 积分趋势
    from datetime import datetime, timezone
    from collections import defaultdict
    
    trend_start = datetime(date.today().year, date.today().month, date.today().day, tzinfo=timezone.utc) - timedelta(days=30)
    pr_list = PointRecord.query.filter(
        PointRecord.user_id == user_id,
        PointRecord.created_at >= trend_start
    ).all()
    
    trend_map = defaultdict(int)
    for pr in pr_list:
        if pr.created_at:
            d = pr.created_at.date() if hasattr(pr.created_at, 'date') else pr.created_at
            trend_map[str(d)] += (pr.points or 0)
    
    # 填充缺失日期
    points_trend = []
    current = trend_start
    end_date = date.today()
    while current <= end_date:
        date_str = current.strftime('%Y-%m-%d')
        points_trend.append({
            'date': date_str,
            'points': trend_map.get(date_str, 0)
        })
        current += timedelta(days=1)
    
    # 段位信息
    tier_info = {
        'current': {
            'name': student.current_tier.display_name if student.current_tier else '未定级',
            'icon': student.current_tier.icon if student.current_tier else '',
            'color': student.current_tier.color if student.current_tier else '#999'
        },
        'peak': {
            'name': student.peak_tier.display_name if student.peak_tier else '未定级',
            'icon': student.peak_tier.icon if student.peak_tier else ''
        },
        'streak_days': student.streak_days or 0
    }
    
    return {
        'basic_info': basic_info,
        'answer_stats': answer_stats,
        'wrong_question_stats': wrong_question_stats,
        'game_stats': game_stats,
        'points_trend': points_trend,
        'tier_info': tier_info
    }


def get_compare_data(category, metric='avg_accuracy', time_range='all'):
    """获取分类间对比数据"""
    overview = get_category_overview(category, time_range)
    
    metric_labels = {
        'avg_accuracy': '平均正确率',
        'avg_points': '平均积分',
        'avg_games': '平均游戏场次',
        'active_ratio': '活跃学生比例'
    }
    
    items = []
    for cat in overview['categories']:
        value = cat.get(metric)
        items.append({
            'name': cat['name'],
            'value': value
        })
    
    # 按value降序
    items.sort(key=lambda x: x['value'] if x['value'] is not None else -1, reverse=True)
    
    return {
        'metric': metric,
        'metric_label': metric_labels.get(metric, metric),
        'items': items
    }


def export_student_data(category, value, time_range='all'):
    """生成导出数据"""
    # 获取所有学生（不分页）
    result = get_category_students(category, value, sort_by='points', page=1, 
                                   per_page=99999, search=None, time_range=time_range)
    return result['students']
