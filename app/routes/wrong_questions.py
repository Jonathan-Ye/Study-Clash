import random
from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app import db, api_login_required
from app.models import (WrongQuestion, WrongQuestionCollection, WrongQuestionCollectionItem, 
                        WrongQuestionNote, ChallengeProgress, ReviewStreak,
                        Question, Subject, Chapter, UserAnswer, 
                        PointRecord, DailyStats, SystemSetting, WRONG_REASONS)

wrong_bp = Blueprint('wrong', __name__)

def get_wrong_question_config():
    config = {
        'consecutive_correct_required': int(SystemSetting.get('wrong_consecutive_correct', 3)),
        'review_points': int(SystemSetting.get('wrong_review_points', 5)),
        'max_review_per_day': int(SystemSetting.get('wrong_max_review_per_day', 50)),
        'enable_spaced_review': SystemSetting.get('wrong_enable_spaced_review', 'true') == 'true',
    }
    return config


# ========== 辅助函数 ==========

def get_streak_info(user_id):
    """获取连续打卡天数和今日状态"""
    today = datetime.now(timezone.utc).date()
    
    today_streak = ReviewStreak.query.filter_by(user_id=user_id, date=today).first()
    today_checked = today_streak is not None
    
    streak_days = 0
    check_date = today
    max_check = 365
    while max_check > 0:
        streak = ReviewStreak.query.filter_by(user_id=user_id, date=check_date).first()
        if streak:
            streak_days += 1
            check_date -= timedelta(days=1)
            max_check -= 1
        else:
            break
    
    if streak_days == 0:
        motivation = '开始你的第一次复习吧！'
    elif streak_days < 3:
        motivation = '加油，坚持复习！'
    elif streak_days < 7:
        motivation = '坚持就是胜利！'
    elif streak_days < 30:
        motivation = '太棒了，你已经养成习惯！'
    else:
        motivation = '学习达人，无人能挡！'
    
    return {
        'streak_days': streak_days,
        'today_checked': today_checked,
        'motivation': motivation
    }


def get_daily_plan_data(user_id):
    """获取每日复习计划数据"""
    max_questions = int(SystemSetting.get('wrong_daily_plan_max_questions', 30))
    
    review_needed = WrongQuestion.get_review_needed(user_id, limit=max_questions)
    
    if not review_needed:
        return {'total': 0, 'chapters': []}
    
    chapter_map = {}
    for wq in review_needed:
        chapter = wq.question.chapter if wq.question else None
        if not chapter:
            continue
        if chapter.id not in chapter_map:
            chapter_map[chapter.id] = {
                'chapter_id': chapter.id,
                'chapter_name': chapter.name,
                'subject_name': chapter.subject.name if chapter.subject else '',
                'count': 0
            }
        chapter_map[chapter.id]['count'] += 1
    
    chapters = sorted(chapter_map.values(), key=lambda x: x['count'], reverse=True)
    
    return {
        'total': len(review_needed),
        'chapters': chapters
    }


def auto_infer_reasons_for_user(user_id):
    """为用户批量自动推断错误原因"""
    unmarked = WrongQuestion.query.filter_by(user_id=user_id, wrong_reason=None).all()
    
    if not unmarked:
        return 0
    
    updated = 0
    
    # 规则1: 最近一次答错且答题时间<5秒 -> 粗心大意
    for wq in unmarked:
        last_answer = UserAnswer.query.filter_by(
            user_id=user_id, question_id=wq.question_id, is_correct=False
        ).order_by(UserAnswer.created_at.desc()).first()
        
        if last_answer and last_answer.time_spent and last_answer.time_spent < 5:
            wq.wrong_reason = 'careless'
            updated += 1
    
    # 规则2: 同章节3题+仍未标注 -> 知识点不熟悉
    chapter_counts = db.session.query(
        Question.chapter_id,
        db.func.count(WrongQuestion.id).label('count')
    ).join(WrongQuestion, Question.id == WrongQuestion.question_id).filter(
        WrongQuestion.user_id == user_id,
        WrongQuestion.wrong_reason.is_(None),
        WrongQuestion.is_mastered == False
    ).group_by(Question.chapter_id).having(
        db.func.count(WrongQuestion.id) >= 3
    ).all()
    
    knowledge_chapters = set(c.chapter_id for c in chapter_counts)
    
    for wq in unmarked:
        if wq.wrong_reason:
            continue
        if wq.question and wq.question.chapter_id in knowledge_chapters:
            wq.wrong_reason = 'knowledge'
            updated += 1
    
    if updated > 0:
        db.session.commit()
    
    return updated


def get_knowledge_map_data(user_id):
    """获取知识点图谱数据"""
    chapter_stats = db.session.query(
        Chapter.id,
        Chapter.name,
        Chapter.subject_id,
        Subject.name.label('subject_name'),
        db.func.count(WrongQuestion.id).label('total'),
        db.func.sum(db.case((WrongQuestion.is_mastered == True, 1), else_=0)).label('mastered')
    ).join(
        Question, Chapter.id == Question.chapter_id
    ).join(
        WrongQuestion, Question.id == WrongQuestion.question_id
    ).join(
        Subject, Chapter.subject_id == Subject.id
    ).filter(
        WrongQuestion.user_id == user_id
    ).group_by(Chapter.id, Chapter.name, Chapter.subject_id, Subject.name).all()
    
    result = []
    for stat in chapter_stats:
        mastery_rate = int((stat.mastered / stat.total) * 100) if stat.total > 0 else 0
        if mastery_rate <= 33:
            color = 'red'
        elif mastery_rate <= 66:
            color = 'yellow'
        else:
            color = 'green'
        
        result.append({
            'chapter_id': stat.id,
            'chapter_name': stat.name,
            'subject_id': stat.subject_id,
            'subject_name': stat.subject_name,
            'total': stat.total,
            'mastered': stat.mastered,
            'mastery_rate': mastery_rate,
            'color': color
        })
    
    subjects = {}
    for item in result:
        subj = item['subject_name']
        if subj not in subjects:
            subjects[subj] = []
        subjects[subj].append(item)
    
    sorted_items = sorted(result, key=lambda x: x['mastery_rate'])[:3]
    
    return {
        'subjects': subjects,
        'weak_top3': sorted_items
    }


def update_review_streak(user_id):
    """更新打卡记录"""
    today = datetime.now(timezone.utc).date()
    streak = ReviewStreak.query.filter_by(user_id=user_id, date=today).first()
    if streak:
        if streak.review_count is None:
            streak.review_count = 0
        streak.review_count += 1
    else:
        streak = ReviewStreak(user_id=user_id, date=today, review_count=1)
        db.session.add(streak)
    db.session.commit()


# ========== 智能复习仪表盘（新默认页） ==========

@wrong_bp.route('/')
@login_required
def dashboard():
    """智能复习仪表盘"""
    # 聚合查询统计数据
    stats_result = db.session.query(
        db.func.count(WrongQuestion.id).label('total'),
        db.func.sum(db.case((WrongQuestion.is_mastered == False, 1), else_=0)).label('not_mastered'),
        db.func.sum(db.case((WrongQuestion.is_mastered == True, 1), else_=0)).label('mastered'),
        db.func.sum(db.case((WrongQuestion.is_important == True, 1), else_=0)).label('important')
    ).filter_by(user_id=current_user.id).first()
    
    stats = {
        'total': stats_result.total or 0,
        'not_mastered': stats_result.not_mastered or 0,
        'mastered': stats_result.mastered or 0,
        'important': stats_result.important or 0,
        'review_today': WrongQuestion.query.filter_by(user_id=current_user.id, is_mastered=False).filter(
            db.or_(WrongQuestion.next_review_at.is_(None), WrongQuestion.next_review_at <= datetime.now(timezone.utc))
        ).count()
    }
    
    # 高频错题(wrong_count>=5且未掌握，最多5条)
    high_freq_wrong = WrongQuestion.query.filter_by(
        user_id=current_user.id, is_mastered=False
    ).filter(WrongQuestion.wrong_count >= 5).order_by(
        WrongQuestion.wrong_count.desc()
    ).limit(5).all()
    
    # 学习打卡记录
    streak_info = get_streak_info(current_user.id)
    
    # 每日计划
    daily_plan = get_daily_plan_data(current_user.id)
    
    # 自动推断错误原因(静默执行)
    try:
        auto_infer_reasons_for_user(current_user.id)
    except Exception as e:
        current_app.logger.error(f'自动推断错误原因失败: {e}')
    
    # 掌握率
    mastery_rate = int((stats['mastered'] / stats['total']) * 100) if stats['total'] > 0 else 0
    
    # 错误原因分布(用于仪表盘可视化)
    reason_stats = db.session.query(
        WrongQuestion.wrong_reason,
        db.func.count(WrongQuestion.id).label('count')
    ).filter(WrongQuestion.user_id == current_user.id).group_by(WrongQuestion.wrong_reason).all()
    
    # 学科分布(用于仪表盘可视化)
    subject_stats = db.session.query(
        Subject.name,
        db.func.count(WrongQuestion.id).label('total'),
        db.func.sum(db.case((WrongQuestion.is_mastered == False, 1), else_=0)).label('not_mastered'),
        db.func.sum(db.case((WrongQuestion.is_mastered == True, 1), else_=0)).label('mastered')
    ).join(Question, Subject.id == Question.subject_id).join(
        WrongQuestion, Question.id == WrongQuestion.question_id
    ).filter(WrongQuestion.user_id == current_user.id).group_by(Subject.id).all()
    
    # 近7天复习趋势
    from collections import defaultdict
    
    start_7 = datetime.now(timezone.utc) - timedelta(days=7)
    ua_review_list = UserAnswer.query.filter(
        UserAnswer.user_id == current_user.id,
        UserAnswer.game_type.in_(['review', 'timed_challenge']),
        UserAnswer.created_at >= start_7
    ).all()
    
    review_map = defaultdict(lambda: {'total': 0, 'correct': 0})
    for ua in ua_review_list:
        if ua.created_at:
            d = ua.created_at.date() if hasattr(ua.created_at, 'date') else ua.created_at
            key = str(d)
            review_map[key]['total'] += 1
            if ua.is_correct:
                review_map[key]['correct'] += 1
    recent_review = [{'date': k, 'total': v['total'], 'correct': v['correct']} for k, v in sorted(review_map.items())]
    
    config = get_wrong_question_config()
    
    return render_template('wrong/dashboard.html',
                          stats=stats,
                          mastery_rate=mastery_rate,
                          high_freq_wrong=high_freq_wrong,
                          streak_info=streak_info,
                          daily_plan=daily_plan,
                          reason_stats=reason_stats,
                          subject_stats=subject_stats,
                          recent_review=recent_review,
                          wrong_reasons=WRONG_REASONS,
                          config=config)


# ========== 错题列表页（原index，保留完整功能） ==========

@wrong_bp.route('/list')
@login_required
def list_view():
    page = request.args.get('page', 1, type=int)
    subject_id = request.args.get('subject_id', type=int)
    chapter_id = request.args.get('chapter_id', type=int)
    is_mastered = request.args.get('is_mastered')
    is_important = request.args.get('is_important')
    wrong_reason = request.args.get('wrong_reason')
    keyword = request.args.get('keyword', '').strip()
    sort_by = request.args.get('sort_by', 'created_at')
    
    query = WrongQuestion.query.filter_by(user_id=current_user.id)
    
    need_join_question = subject_id or chapter_id or keyword
    if need_join_question:
        query = query.join(Question)
        if subject_id:
            query = query.filter(Question.subject_id == subject_id)
        if chapter_id:
            query = query.filter(Question.chapter_id == chapter_id)
    
    if is_mastered == '1':
        query = query.filter_by(is_mastered=True)
    elif is_mastered == '0':
        query = query.filter_by(is_mastered=False)
    
    if is_important == '1':
        query = query.filter_by(is_important=True)
    
    if wrong_reason:
        query = query.filter_by(wrong_reason=wrong_reason)
    
    if keyword:
        query = query.filter(Question.content.contains(keyword))
    
    if sort_by == 'wrong_count':
        query = query.order_by(WrongQuestion.wrong_count.desc())
    elif sort_by == 'review_count':
        query = query.order_by(WrongQuestion.review_count.desc())
    elif sort_by == 'next_review':
        query = query.order_by(WrongQuestion.next_review_at.asc().nulls_first())
    elif sort_by == 'important':
        query = query.order_by(WrongQuestion.is_important.desc(), WrongQuestion.created_at.desc())
    else:
        query = query.order_by(WrongQuestion.created_at.desc())
    
    pagination = query.paginate(page=page, per_page=20)
    
    subjects = Subject.query.filter_by(is_active=True).all()
    user_major = getattr(current_user, 'major', None)
    filtered_subjects = [s for s in subjects if s.is_applicable_for_major(user_major)]
    
    chapters = []
    if subject_id:
        chapters = Chapter.query.filter_by(subject_id=subject_id, is_active=True).order_by(Chapter.order).all()
    
    stats_result = db.session.query(
        db.func.count(WrongQuestion.id).label('total'),
        db.func.sum(db.case((WrongQuestion.is_mastered == False, 1), else_=0)).label('not_mastered'),
        db.func.sum(db.case((WrongQuestion.is_mastered == True, 1), else_=0)).label('mastered'),
        db.func.sum(db.case((WrongQuestion.is_important == True, 1), else_=0)).label('important')
    ).filter_by(user_id=current_user.id).first()
    
    stats = {
        'total': stats_result.total or 0,
        'not_mastered': stats_result.not_mastered or 0,
        'mastered': stats_result.mastered or 0,
        'important': stats_result.important or 0,
        'review_today': WrongQuestion.query.filter_by(user_id=current_user.id, is_mastered=False).filter(
            db.or_(WrongQuestion.next_review_at.is_(None), WrongQuestion.next_review_at <= datetime.now(timezone.utc))
        ).count()
    }
    
    reason_stats = db.session.query(
        WrongQuestion.wrong_reason,
        db.func.count(WrongQuestion.id).label('count')
    ).filter(WrongQuestion.user_id == current_user.id).group_by(WrongQuestion.wrong_reason).all()
    
    stats['by_reason'] = {r.wrong_reason or 'unmarked': r.count for r in reason_stats}
    
    config = get_wrong_question_config()
    
    return render_template('wrong/index.html', 
                          pagination=pagination, 
                          subjects=filtered_subjects,
                          chapters=chapters,
                          stats=stats,
                          wrong_reasons=WRONG_REASONS,
                          config=config)


# ========== 闯关模式 ==========

@wrong_bp.route('/challenge')
@login_required
def challenge():
    """闯关模式 - 关卡列表"""
    chapter_stats = db.session.query(
        Chapter.id,
        Chapter.name,
        Subject.name.label('subject_name'),
        db.func.count(WrongQuestion.id).label('wrong_count')
    ).join(
        Question, Chapter.id == Question.chapter_id
    ).join(
        WrongQuestion, Question.id == WrongQuestion.question_id
    ).join(
        Subject, Chapter.subject_id == Subject.id
    ).filter(
        WrongQuestion.user_id == current_user.id,
        WrongQuestion.is_mastered == False
    ).group_by(Chapter.id, Chapter.name, Subject.name).order_by(
        db.func.count(WrongQuestion.id).desc()
    ).all()
    
    if not chapter_stats:
        flash('恭喜！所有错题已掌握', 'success')
        return redirect(url_for('wrong.dashboard'))
    
    cleared_chapters = set(
        cp.chapter_id for cp in 
        ChallengeProgress.query.filter_by(user_id=current_user.id, is_cleared=True).all()
    )
    
    levels = []
    for i, stat in enumerate(chapter_stats):
        is_cleared = stat.id in cleared_chapters
        is_unlocked = (i == 0) or (chapter_stats[i-1].id in cleared_chapters)
        levels.append({
            'level': i + 1,
            'chapter_id': stat.id,
            'chapter_name': stat.name,
            'subject_name': stat.subject_name,
            'wrong_count': stat.wrong_count,
            'is_cleared': is_cleared,
            'is_unlocked': is_unlocked or is_cleared
        })
    
    questions_per_level = int(SystemSetting.get('wrong_challenge_questions_per_level', 10))
    
    return render_template('wrong/challenge.html',
                          levels=levels,
                          questions_per_level=questions_per_level)


@wrong_bp.route('/challenge/<int:chapter_id>')
@login_required
def challenge_level(chapter_id):
    """闯关模式 - 进入某关卡"""
    questions_per_level = int(SystemSetting.get('wrong_challenge_questions_per_level', 10))
    
    wrong_questions = WrongQuestion.query.filter_by(
        user_id=current_user.id, is_mastered=False
    ).join(Question).filter(Question.chapter_id == chapter_id).order_by(
        WrongQuestion.wrong_count.desc()
    ).limit(questions_per_level).all()
    
    if not wrong_questions:
        flash('该章节没有需要复习的错题', 'info')
        return redirect(url_for('wrong.challenge'))
    
    config = get_wrong_question_config()
    
    return render_template('wrong/review.html',
                          wrong_questions=wrong_questions,
                          subjects=Subject.query.filter_by(is_active=True).all(),
                          config=config,
                          is_challenge=True,
                          chapter_id=chapter_id)


@wrong_bp.route('/api/challenge-progress', methods=['GET', 'POST'])
@login_required
def challenge_progress_api():
    """查询或更新关卡通关状态"""
    if request.method == 'GET':
        progress = ChallengeProgress.query.filter_by(user_id=current_user.id).all()
        return jsonify({
            'progress': [{
                'chapter_id': p.chapter_id,
                'is_cleared': p.is_cleared,
                'cleared_at': p.cleared_at.strftime('%Y-%m-%d %H:%M') if p.cleared_at else None
            } for p in progress]
        })
    
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': '无效请求数据'}), 400
    
    chapter_id = data.get('chapter_id')
    is_cleared = data.get('is_cleared', False)
    
    if not chapter_id:
        return jsonify({'error': '缺少chapter_id'}), 400
    
    progress = ChallengeProgress.query.filter_by(
        user_id=current_user.id, chapter_id=chapter_id
    ).first()
    
    if progress:
        progress.is_cleared = is_cleared
        if is_cleared:
            progress.cleared_at = datetime.now(timezone.utc)
    else:
        progress = ChallengeProgress(
            user_id=current_user.id,
            chapter_id=chapter_id,
            is_cleared=is_cleared,
            cleared_at=datetime.now(timezone.utc) if is_cleared else None
        )
        db.session.add(progress)
    
    db.session.commit()
    
    return jsonify({'success': True, 'is_cleared': is_cleared})


# ========== 限时挑战 ==========

@wrong_bp.route('/timed-challenge')
@login_required
def timed_challenge():
    """限时挑战"""
    timed_questions_count = int(SystemSetting.get('wrong_timed_challenge_questions', 10))
    timed_seconds = int(SystemSetting.get('wrong_timed_challenge_seconds', 30))
    
    from app.services.question_recommendation import get_smart_review_questions
    review_pool = get_smart_review_questions(current_user.id, limit=timed_questions_count * 3)
    
    if not review_pool:
        flash('暂无待复习错题', 'info')
        return redirect(url_for('wrong.dashboard'))
    
    # 保留所有对象（WrongQuestion和Question都可以）
    wrong_questions = random.sample(review_pool, min(timed_questions_count, len(review_pool)))
    
    config = get_wrong_question_config()
    
    return render_template('wrong/timed_challenge.html',
                          wrong_questions=wrong_questions,
                          timed_seconds=timed_seconds,
                          config=config)


@wrong_bp.route('/api/timed-submit', methods=['POST'])
@api_login_required
def timed_submit():
    """限时挑战提交"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': '无效请求数据'}), 400
    
    wrong_question_id = data.get('wrong_question_id')
    question_id = data.get('question_id')
    answer = data.get('answer')
    is_timeout = data.get('is_timeout', False)
    time_spent = data.get('time_spent', 0)
    
    if answer is None:
        return jsonify({'error': '缺少必要参数'}), 400
    
    config = get_wrong_question_config()
    
    # 支持两种模式：wrong_question_id 或 question_id
    wrong_question = None
    question = None
    
    if wrong_question_id:
        # 普通模式：通过wrong_question_id查找
        wrong_question = WrongQuestion.query.get(wrong_question_id)
        if not wrong_question or wrong_question.user_id != current_user.id:
            return jsonify({'error': '无效请求'}), 400
        question = wrong_question.question
    elif question_id:
        # 智能推荐模式：通过question_id查找或创建WrongQuestion
        question = Question.query.get(question_id)
        if not question:
            return jsonify({'error': '题目不存在'}), 400
        
        # 查找或创建WrongQuestion记录
        wrong_question = WrongQuestion.query.filter_by(
            user_id=current_user.id,
            question_id=question_id
        ).first()
        
        if not wrong_question:
            wrong_question = WrongQuestion(
                user_id=current_user.id,
                question_id=question_id,
                wrong_count=0,
                is_mastered=False
            )
            db.session.add(wrong_question)
            db.session.flush()
    else:
        return jsonify({'error': '缺少wrong_question_id或question_id'}), 400
    
    if is_timeout:
        is_correct = False
        if not answer:
            answer = ''
    else:
        is_correct = question.check_answer(answer)
    
    config = get_wrong_question_config()
    
    try:
        user_answer = UserAnswer()
        user_answer.user_id = current_user.id
        user_answer.question_id = question.id
        user_answer.user_answer = answer
        user_answer.is_correct = is_correct
        user_answer.time_spent = time_spent
        user_answer.game_type = 'timed_challenge'
        db.session.add(user_answer)
        
        points_earned = 0
        is_mastered = False
        
        if is_correct:
            is_mastered = wrong_question.mark_correct_in_review(config['consecutive_correct_required'])
            if is_mastered:
                points_earned = config['review_points']
                if points_earned > 0:
                    current_user.add_points(points_earned, 'review_mastered')
            else:
                points_earned = max(1, config['review_points'] // 3) if config['review_points'] > 0 else 1
                current_user.add_points(points_earned, 'review_correct')
            
            stats = DailyStats.get_or_create(current_user.id)
            stats.update_answer(True, time_spent)
            if stats.points_earned is None:
                stats.points_earned = 0
            stats.points_earned += points_earned
        else:
            wrong_question.mark_wrong_in_review(answer)
            stats = DailyStats.get_or_create(current_user.id)
            stats.update_answer(False, time_spent)
        
        db.session.commit()
        update_review_streak(current_user.id)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'限时挑战提交失败: {e}')
        return jsonify({'error': '提交失败，请重试'}), 500
    
    similar_questions = []
    if not is_correct:
        similar_questions = [q.to_dict() for q in WrongQuestion.get_similar_questions(question.id, 3, user_id=current_user.id)]
    
    return jsonify({
        'is_correct': is_correct,
        'is_timeout': is_timeout,
        'correct_answer': question.correct_answer,
        'analysis': question.analysis,
        'points_earned': points_earned,
        'is_mastered': is_mastered,
        'consecutive_correct': wrong_question.consecutive_correct,
        'consecutive_required': config['consecutive_correct_required'],
        'similar_questions': similar_questions
    })


# ========== 薄弱专练 ==========

@wrong_bp.route('/weak-practice')
@login_required
def weak_practice():
    """薄弱专练 - 章节选择"""
    weak_points = WrongQuestion.get_weak_points(current_user.id, limit=3)
    
    if not weak_points:
        flash('太棒了！没有薄弱知识点', 'success')
        return redirect(url_for('wrong.dashboard'))
    
    return render_template('wrong/weak_practice.html', weak_points=weak_points)


@wrong_bp.route('/weak-practice/<int:chapter_id>')
@login_required
def weak_practice_chapter(chapter_id):
    """薄弱专练 - 进入某章节复习"""
    from app.services.question_recommendation import get_smart_specialized_practice
    questions = get_smart_specialized_practice(current_user.id, chapter_id, count=20)
    
    if not questions:
        flash('该章节没有需要复习的错题', 'info')
        return redirect(url_for('wrong.weak_practice'))
    
    wrong_questions = [q for q in questions if q]
    
    config = get_wrong_question_config()
    
    return render_template('wrong/review.html',
                          wrong_questions=wrong_questions,
                          subjects=Subject.query.filter_by(is_active=True).all(),
                          config=config)


# ========== 知识点掌握图谱 ==========

@wrong_bp.route('/knowledge-map')
@login_required
def knowledge_map():
    """知识点掌握图谱"""
    map_data = get_knowledge_map_data(current_user.id)
    
    if not map_data['subjects']:
        flash('暂无错题记录，继续加油！', 'info')
        return redirect(url_for('wrong.dashboard'))
    
    return render_template('wrong/knowledge_map.html', map_data=map_data)


@wrong_bp.route('/api/knowledge-map')
@login_required
def api_knowledge_map():
    """知识点图谱数据API"""
    map_data = get_knowledge_map_data(current_user.id)
    return jsonify(map_data)


# ========== 每日复习计划 ==========

@wrong_bp.route('/daily-plan')
@login_required
def daily_plan():
    """每日复习计划"""
    plan_data = get_daily_plan_data(current_user.id)
    streak_info = get_streak_info(current_user.id)
    
    return render_template('wrong/daily_plan.html',
                          plan_data=plan_data,
                          streak_info=streak_info)


@wrong_bp.route('/api/streak')
@login_required
def get_streak():
    """查询打卡记录"""
    streak_info = get_streak_info(current_user.id)
    return jsonify(streak_info)


# ========== 自动推断错误原因 ==========

@wrong_bp.route('/api/auto-infer-reasons', methods=['POST'])
@login_required
def auto_infer_reasons_api():
    """批量自动推断错误原因"""
    try:
        updated = auto_infer_reasons_for_user(current_user.id)
        return jsonify({'success': True, 'updated_count': updated})
    except Exception as e:
        current_app.logger.error(f'自动推断错误原因失败: {e}')
        return jsonify({'error': '推断失败'}), 500


# ========== 以下为保留的原有路由 ==========

@wrong_bp.route('/analysis')
@login_required
def analysis():
    weak_points = WrongQuestion.get_weak_points(current_user.id, limit=10)
    
    subject_stats = db.session.query(
        Subject.name,
        db.func.count(WrongQuestion.id).label('total'),
        db.func.sum(db.case((WrongQuestion.is_mastered == False, 1), else_=0)).label('not_mastered'),
        db.func.sum(db.case((WrongQuestion.is_mastered == True, 1), else_=0)).label('mastered'),
        db.func.avg(WrongQuestion.wrong_count).label('avg_wrong')
    ).join(
        Question, Subject.id == Question.subject_id
    ).join(
        WrongQuestion, Question.id == WrongQuestion.question_id
    ).filter(
        WrongQuestion.user_id == current_user.id
    ).group_by(Subject.id).all()
    
    difficulty_stats = db.session.query(
        Question.difficulty,
        db.func.count(WrongQuestion.id).label('count')
    ).join(
        WrongQuestion, Question.id == WrongQuestion.question_id
    ).filter(
        WrongQuestion.user_id == current_user.id
    ).group_by(Question.difficulty).all()
    
    reason_stats = db.session.query(
        WrongQuestion.wrong_reason,
        db.func.count(WrongQuestion.id).label('count')
    ).filter(
        WrongQuestion.user_id == current_user.id
    ).group_by(WrongQuestion.wrong_reason).all()
    
    from collections import defaultdict
    
    start_30 = datetime.now(timezone.utc) - timedelta(days=30)
    
    wq_list = WrongQuestion.query.filter(
        WrongQuestion.user_id == current_user.id,
        WrongQuestion.created_at >= start_30
    ).all()
    
    trend_map = defaultdict(int)
    for wq in wq_list:
        if wq.created_at:
            d = wq.created_at.date() if hasattr(wq.created_at, 'date') else wq.created_at
            trend_map[str(d)] += 1
    recent_trend = [{'date': k, 'count': v} for k, v in sorted(trend_map.items())]
    
    ua_list = UserAnswer.query.filter(
        UserAnswer.user_id == current_user.id,
        UserAnswer.game_type == 'review',
        UserAnswer.created_at >= start_30
    ).all()
    
    review_map = defaultdict(lambda: {'total': 0, 'correct': 0})
    for ua in ua_list:
        if ua.created_at:
            d = ua.created_at.date() if hasattr(ua.created_at, 'date') else ua.created_at
            key = str(d)
            review_map[key]['total'] += 1
            if ua.is_correct:
                review_map[key]['correct'] += 1
    review_trend = [{'date': k, 'total': v['total'], 'correct': v['correct']} for k, v in sorted(review_map.items())]
    
    now_utc = datetime.now(timezone.utc)
    end_14 = now_utc + timedelta(days=14)
    upcoming_list = WrongQuestion.query.filter(
        WrongQuestion.user_id == current_user.id,
        WrongQuestion.is_mastered == False,
        WrongQuestion.next_review_at >= now_utc,
        WrongQuestion.next_review_at <= end_14
    ).all()
    
    upcoming_map = defaultdict(int)
    for wq in upcoming_list:
        if wq.next_review_at:
            d = wq.next_review_at.date() if hasattr(wq.next_review_at, 'date') else wq.next_review_at
            upcoming_map[str(d)] += 1
    upcoming_reviews = [{'date': k, 'count': v} for k, v in sorted(upcoming_map.items())]
    
    review_forecast = defaultdict(int)
    today = datetime.now(timezone.utc).date()
    
    for i in range(14):
        date = today + timedelta(days=i)
        review_forecast[date.isoformat()] = 0
    
    for item in upcoming_reviews:
        if item['date']:
            review_forecast[item['date']] = item['count']
    
    no_schedule_count = WrongQuestion.query.filter_by(
        user_id=current_user.id,
        is_mastered=False
    ).filter(
        WrongQuestion.next_review_at.is_(None)
    ).count()
    
    today = datetime.now(timezone.utc).date()
    forecast_dates = []
    week_total = 0
    
    for i in range(14):
        date = today + timedelta(days=i)
        forecast_dates.append(date.isoformat())
        if i < 7:
            week_total += review_forecast.get(date, 0)
    
    knowledge_map_data = get_knowledge_map_data(current_user.id)

    return render_template('wrong/analysis.html',
                          weak_points=weak_points,
                          subject_stats=subject_stats,
                          difficulty_stats=difficulty_stats,
                          reason_stats=reason_stats,
                          recent_trend=recent_trend,
                          review_trend=review_trend,
                          review_forecast=review_forecast,
                          forecast_dates=forecast_dates,
                          today=today.isoformat(),
                          week_total=week_total,
                          no_schedule_count=no_schedule_count,
                          wrong_reasons=WRONG_REASONS,
                          knowledge_map_data=knowledge_map_data)

@wrong_bp.route('/review')
@login_required
def review():
    subject_id = request.args.get('subject_id', type=int)
    chapter_id = request.args.get('chapter_id', type=int)
    mode = request.args.get('mode', 'all')
    
    config = get_wrong_question_config()
    max_questions = config['max_review_per_day']
    
    if mode == 'spaced' and config['enable_spaced_review']:
        from app.services.question_recommendation import get_smart_review_questions
        questions = get_smart_review_questions(current_user.id, limit=max_questions)
        # 确保都是Question对象（过滤掉None和无效数据）
        wrong_questions = [q for q in questions if q is not None and hasattr(q, 'content')]
    else:
        query = WrongQuestion.query.filter_by(user_id=current_user.id, is_mastered=False)
        
        if subject_id:
            query = query.join(Question).filter(Question.subject_id == subject_id)
        
        if chapter_id:
            query = query.join(Question).filter(Question.chapter_id == chapter_id)
        
        wrong_questions = query.order_by(
            WrongQuestion.is_important.desc(),
            WrongQuestion.wrong_count.desc()
        ).limit(max_questions).all()
    
    # 过滤掉无效数据
    if mode == 'spaced' and config['enable_spaced_review']:
        # 对于智能推荐模式，wrong_questions已经是Question对象列表
        pass
    else:
        # 对于普通模式，过滤掉题目已被删除的错题记录
        wrong_questions = [wq for wq in wrong_questions if wq.question is not None]
    
    if not wrong_questions:
        flash('没有需要复习的错题', 'info')
        return redirect(url_for('wrong.dashboard'))
    
    subjects = Subject.query.filter_by(is_active=True).all()
    user_major = getattr(current_user, 'major', None)
    filtered_subjects = [s for s in subjects if s.is_applicable_for_major(user_major)]
    
    return render_template('wrong/review.html', 
                          wrong_questions=wrong_questions,
                          subjects=filtered_subjects,
                          config=config)

@wrong_bp.route('/api/submit-review', methods=['POST'])
@api_login_required
def submit_review():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': '无效请求数据'}), 400
    
    wrong_question_id = data.get('wrong_question_id')
    question_id = data.get('question_id')
    answer = data.get('answer')
    time_spent = data.get('time_spent', 0)
    
    if answer is None:
        return jsonify({'error': '缺少必要参数'}), 400
    
    config = get_wrong_question_config()
    
    # 支持两种模式：wrong_question_id 或 question_id
    wrong_question = None
    question = None
    
    if wrong_question_id:
        # 普通模式：通过wrong_question_id查找
        wrong_question = WrongQuestion.query.get(wrong_question_id)
        if not wrong_question or wrong_question.user_id != current_user.id:
            return jsonify({'error': '无效请求'}), 400
        question = wrong_question.question
    elif question_id:
        # 智能推荐模式：通过question_id查找或创建WrongQuestion
        question = Question.query.get(question_id)
        if not question:
            return jsonify({'error': '题目不存在'}), 400
        
        # 查找或创建WrongQuestion记录
        wrong_question = WrongQuestion.query.filter_by(
            user_id=current_user.id,
            question_id=question_id
        ).first()
        
        if not wrong_question:
            wrong_question = WrongQuestion(
                user_id=current_user.id,
                question_id=question_id,
                wrong_count=0,
                is_mastered=False
            )
            db.session.add(wrong_question)
            db.session.flush()
    else:
        return jsonify({'error': '缺少wrong_question_id或question_id'}), 400
    
    is_correct = question.check_answer(answer)
    
    config = get_wrong_question_config()
    
    try:
        user_answer = UserAnswer()
        user_answer.user_id = current_user.id
        user_answer.question_id = question.id
        user_answer.user_answer = answer
        user_answer.is_correct = is_correct
        user_answer.time_spent = time_spent
        user_answer.game_type = 'review'
        
        db.session.add(user_answer)
        
        points_earned = 0
        is_mastered = False
        
        if is_correct:
            is_mastered = wrong_question.mark_correct_in_review(config['consecutive_correct_required'])
            
            if is_mastered:
                points_earned = config['review_points']
                if points_earned > 0:
                    current_user.add_points(points_earned, 'review_mastered')
            else:
                points_earned = max(1, config['review_points'] // 3) if config['review_points'] > 0 else 1
                current_user.add_points(points_earned, 'review_correct')
            
            stats = DailyStats.get_or_create(current_user.id)
            stats.update_answer(True, time_spent)
            if stats.points_earned is None:
                stats.points_earned = 0
            stats.points_earned += points_earned
        else:
            wrong_question.mark_wrong_in_review(answer)
            
            stats = DailyStats.get_or_create(current_user.id)
            stats.update_answer(False, time_spent)
        
        db.session.commit()
        update_review_streak(current_user.id)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'复习提交失败: {e}')
        return jsonify({'error': '提交失败，请重试'}), 500
    
    similar_questions = []
    if not is_correct:
        similar_questions = [q.to_dict() for q in WrongQuestion.get_similar_questions(question.id, 3, user_id=current_user.id)]
    
    return jsonify({
        'is_correct': is_correct,
        'correct_answer': question.correct_answer,
        'analysis': question.analysis,
        'points_earned': points_earned,
        'is_mastered': is_mastered,
        'consecutive_correct': wrong_question.consecutive_correct,
        'consecutive_required': config['consecutive_correct_required'],
        'next_review_at': wrong_question.next_review_at.strftime('%Y-%m-%d') if wrong_question.next_review_at else None,
        'similar_questions': similar_questions
    })

@wrong_bp.route('/<int:id>/detail')
@login_required
def detail(id):
    wrong_question = WrongQuestion.query.get_or_404(id)
    
    if wrong_question.user_id != current_user.id:
        return jsonify({'error': '无权访问'}), 403
    
    similar_questions = WrongQuestion.get_similar_questions(wrong_question.question_id, 5, user_id=current_user.id)
    
    return jsonify({
        'wrong': wrong_question.to_dict(),
        'similar_questions': [q.to_dict() for q in similar_questions]
    })

@wrong_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    wrong_question = WrongQuestion.query.get_or_404(id)
    
    if wrong_question.user_id != current_user.id:
        flash('无权操作', 'error')
        return redirect(url_for('wrong.list_view'))
    
    WrongQuestionCollectionItem.query.filter_by(wrong_question_id=id).delete()
    WrongQuestionNote.query.filter_by(wrong_question_id=id).delete()
    
    db.session.delete(wrong_question)
    db.session.commit()
    
    flash('错题已删除', 'success')
    return redirect(url_for('wrong.list_view'))

@wrong_bp.route('/<int:id>/master', methods=['POST'])
@login_required
def mark_mastered(id):
    wrong_question = WrongQuestion.query.get_or_404(id)
    
    if wrong_question.user_id != current_user.id:
        return jsonify({'error': '无权操作'}), 403
    
    config = get_wrong_question_config()
    wrong_question.mark_mastered(consecutive_required=config['consecutive_correct_required'])
    db.session.commit()
    
    return jsonify({'success': True, 'is_mastered': True})

@wrong_bp.route('/<int:id>/toggle-important', methods=['POST'])
@login_required
def toggle_important(id):
    wrong_question = WrongQuestion.query.get_or_404(id)
    
    if wrong_question.user_id != current_user.id:
        return jsonify({'error': '无权操作'}), 403
    
    wrong_question.toggle_important()
    db.session.commit()
    
    return jsonify({'success': True, 'is_important': wrong_question.is_important})

@wrong_bp.route('/<int:id>/set-reason', methods=['POST'])
@login_required
def set_reason(id):
    wrong_question = WrongQuestion.query.get_or_404(id)
    
    if wrong_question.user_id != current_user.id:
        return jsonify({'error': '无权操作'}), 403
    
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': '无效请求数据'}), 400
    
    reason = data.get('reason')
    if reason not in WRONG_REASONS:
        return jsonify({'error': '无效的错误原因'}), 400
    
    wrong_question.wrong_reason = reason
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'wrong_reason': wrong_question.wrong_reason,
        'wrong_reason_display': wrong_question.get_wrong_reason_display()
    })

@wrong_bp.route('/<int:id>/note', methods=['POST'])
@login_required
def save_note(id):
    wrong_question = WrongQuestion.query.get_or_404(id)
    
    if wrong_question.user_id != current_user.id:
        return jsonify({'error': '无权操作'}), 403
    
    note = request.get_json().get('note', '')
    wrong_question.note = note
    db.session.commit()
    
    return jsonify({'success': True})

@wrong_bp.route('/batch-master', methods=['POST'])
@login_required
def batch_master():
    ids = request.form.getlist('ids', type=int)
    
    if not ids:
        flash('请选择要标记的错题', 'error')
        return redirect(url_for('wrong.list_view'))
    
    if len(ids) > 100:
        flash('一次最多标记100道错题', 'error')
        return redirect(url_for('wrong.list_view'))
    
    config = get_wrong_question_config()
    consecutive_required = config['consecutive_correct_required']
    
    count = WrongQuestion.query.filter(
        WrongQuestion.id.in_(ids),
        WrongQuestion.user_id == current_user.id
    ).update({
        'is_mastered': True, 
        'mastered_at': datetime.now(timezone.utc),
        'consecutive_correct': consecutive_required,
        'next_review_at': datetime.now(timezone.utc) + timedelta(days=30)
    }, synchronize_session=False)
    
    db.session.commit()
    
    flash(f'已标记{count}道错题为已掌握', 'success')
    return redirect(url_for('wrong.list_view'))

@wrong_bp.route('/batch-delete', methods=['POST'])
@login_required
def batch_delete():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': '无效请求数据'}), 400
    
    ids = data.get('ids', [])
    
    if not ids:
        return jsonify({'error': '请选择要删除的错题'}), 400
    
    if len(ids) > 100:
        return jsonify({'error': '一次最多删除100道错题'}), 400
    
    WrongQuestionCollectionItem.query.filter(
        WrongQuestionCollectionItem.wrong_question_id.in_(ids)
    ).delete(synchronize_session=False)
    
    WrongQuestionNote.query.filter(
        WrongQuestionNote.wrong_question_id.in_(ids)
    ).delete(synchronize_session=False)
    
    count = WrongQuestion.query.filter(
        WrongQuestion.id.in_(ids),
        WrongQuestion.user_id == current_user.id
    ).delete(synchronize_session=False)
    
    db.session.commit()
    
    return jsonify({'success': True, 'deleted_count': count})

@wrong_bp.route('/batch-set-reason', methods=['POST'])
@login_required
def batch_set_reason():
    data = request.get_json()
    ids = data.get('ids', [])
    reason = data.get('reason')
    
    if not ids:
        return jsonify({'error': '请选择错题'}), 400
    
    if reason not in WRONG_REASONS:
        return jsonify({'error': '无效的错误原因'}), 400
    
    count = WrongQuestion.query.filter(
        WrongQuestion.id.in_(ids),
        WrongQuestion.user_id == current_user.id
    ).update({'wrong_reason': reason}, synchronize_session=False)
    
    db.session.commit()
    
    return jsonify({'success': True, 'updated_count': count})

@wrong_bp.route('/collection')
@login_required
def collections():
    collections = WrongQuestionCollection.query.filter_by(user_id=current_user.id).all()
    
    return render_template('wrong/collections.html', collections=collections)

@wrong_bp.route('/collection/create', methods=['GET', 'POST'])
@login_required
def create_collection():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '')
        is_public = request.form.get('is_public') == 'on'
        
        if not name or len(name) > 100:
            flash('收藏夹名称不能为空且不能超过100字符', 'error')
            return redirect(url_for('wrong.create_collection'))
        
        existing = WrongQuestionCollection.query.filter_by(user_id=current_user.id, name=name).first()
        if existing:
            flash('已存在同名收藏夹', 'error')
            return redirect(url_for('wrong.create_collection'))
        
        collection = WrongQuestionCollection()
        collection.user_id = current_user.id
        collection.name = name
        collection.description = description
        collection.is_public = is_public
        
        db.session.add(collection)
        db.session.commit()
        
        flash('收藏夹创建成功', 'success')
        return redirect(url_for('wrong.collections'))
    
    return render_template('wrong/create_collection.html')

@wrong_bp.route('/collection/<int:collection_id>')
@login_required
def view_collection(collection_id):
    collection = WrongQuestionCollection.query.get_or_404(collection_id)
    
    if collection.user_id != current_user.id and not collection.is_public:
        flash('无权访问此收藏夹', 'error')
        return redirect(url_for('wrong.collections'))
    
    items = WrongQuestionCollectionItem.query.filter_by(collection_id=collection_id).all()
    
    return render_template('wrong/view_collection.html', collection=collection, items=items)

@wrong_bp.route('/collection/<int:collection_id>/add', methods=['POST'])
@login_required
def add_to_collection(collection_id):
    collection = WrongQuestionCollection.query.get_or_404(collection_id)
    
    if collection.user_id != current_user.id:
        return jsonify({'error': '无权操作'}), 403
    
    wrong_question_id = request.form.get('wrong_question_id', type=int)
    note = request.form.get('note')
    
    existing = WrongQuestionCollectionItem.query.filter_by(
        collection_id=collection_id,
        wrong_question_id=wrong_question_id
    ).first()
    
    if existing:
        return jsonify({'error': '该错题已在收藏夹中'}), 400
    
    item = WrongQuestionCollectionItem()
    item.collection_id = collection_id
    item.wrong_question_id = wrong_question_id
    item.note = note
    
    db.session.add(item)
    db.session.commit()
    
    return jsonify({'success': True})

@wrong_bp.route('/collection/<int:collection_id>/delete', methods=['POST'])
@login_required
def delete_collection(collection_id):
    collection = WrongQuestionCollection.query.get_or_404(collection_id)
    
    if collection.user_id != current_user.id:
        flash('无权操作', 'error')
        return redirect(url_for('wrong.collections'))
    
    db.session.delete(collection)
    db.session.commit()
    
    flash('收藏夹已删除', 'success')
    return redirect(url_for('wrong.collections'))

@wrong_bp.route('/api/stats')
@login_required
def api_stats():
    total = WrongQuestion.query.filter_by(user_id=current_user.id).count()
    not_mastered = WrongQuestion.query.filter_by(user_id=current_user.id, is_mastered=False).count()
    mastered = WrongQuestion.query.filter_by(user_id=current_user.id, is_mastered=True).count()
    
    subject_stats = db.session.query(
        Subject.name,
        db.func.count(WrongQuestion.id).label('count')
    ).join(Question, Subject.id == Question.subject_id)\
     .join(WrongQuestion, Question.id == WrongQuestion.question_id)\
     .filter(WrongQuestion.user_id == current_user.id)\
     .group_by(Subject.id)\
     .all()
    
    difficulty_stats = db.session.query(
        Question.difficulty,
        db.func.count(WrongQuestion.id).label('count')
    ).join(WrongQuestion, Question.id == WrongQuestion.question_id)\
     .filter(WrongQuestion.user_id == current_user.id)\
     .group_by(Question.difficulty)\
     .all()
    
    reason_stats = db.session.query(
        WrongQuestion.wrong_reason,
        db.func.count(WrongQuestion.id).label('count')
    ).filter(
        WrongQuestion.user_id == current_user.id
    ).group_by(WrongQuestion.wrong_reason).all()
    
    return jsonify({
        'total': total,
        'not_mastered': not_mastered,
        'mastered': mastered,
        'by_subject': [{'subject': s.name, 'count': s.count} for s in subject_stats],
        'by_difficulty': [{'difficulty': d.difficulty, 'count': d.count} for d in difficulty_stats],
        'by_reason': [{'reason': r.wrong_reason, 'reason_display': WRONG_REASONS.get(r.wrong_reason, '未标注'), 'count': r.count} for r in reason_stats]
    })

@wrong_bp.route('/api/recommend')
@login_required
def api_recommend():
    config = get_wrong_question_config()
    
    review_needed = WrongQuestion.get_review_needed(current_user.id, limit=10)
    
    weak_points = WrongQuestion.get_weak_points(current_user.id, limit=5)
    
    return jsonify({
        'review_needed': [w.to_dict() for w in review_needed],
        'weak_points': [{
            'chapter_id': w.id,
            'chapter_name': w.name,
            'subject_name': w.subject_name,
            'wrong_count': w.wrong_count,
            'not_mastered_count': w.not_mastered_count
        } for w in weak_points]
    })

@wrong_bp.route('/api/chapters-by-subject/<int:subject_id>')
@login_required
def api_chapters_by_subject(subject_id):
    chapters = Chapter.query.filter_by(subject_id=subject_id, is_active=True).order_by(Chapter.order).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'level': c.level
    } for c in chapters])
