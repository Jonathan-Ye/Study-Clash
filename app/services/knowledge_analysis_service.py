"""教师知识点分析服务层

为教师提供班级/专业维度的知识点掌握度分析，包括：
- 知识点掌握度概览（按章节聚合）
- 章节钻取详情（题目级分析）
- 班级/专业对比分析
- 薄弱知识点预警
- 教学建议
"""
from datetime import datetime, timedelta, date
from app import db
from app.models import (User, UserAnswer, WrongQuestion, 
                        Subject, Chapter, Question, DictionaryItem)


# ==================== 常量 ====================

MASTERY_LEVELS = {
    'excellent': {'label': '优秀', 'color': '#198754', 'min_rate': 85},
    'good': {'label': '良好', 'color': '#0d6efd', 'min_rate': 70},
    'average': {'label': '一般', 'color': '#ffc107', 'min_rate': 60},
    'weak': {'label': '薄弱', 'color': '#fd7e14', 'min_rate': 40},
    'severe_weak': {'label': '严重薄弱', 'color': '#dc3545', 'min_rate': 0},
}

SUGGESTION_TEMPLATES = {
    'severe_weak': '建议安排专项复习课，重点讲解{chapter}相关概念和例题',
    'weak': '建议增加课堂练习，针对{chapter}易错点进行强化训练',
    'average': '建议针对性讲解{chapter}的易错点，巩固薄弱环节',
}

HIGH_FREQ_ERROR_THRESHOLD = 30  # 高频错题阈值：错误率>=30%
SIGNIFICANT_DIFF_THRESHOLD = 20  # 显著差异阈值：差异>20%


# ==================== 辅助方法 ====================

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


def _calculate_mastery_level(correct_rate):
    """根据正确率计算掌握等级"""
    if correct_rate is None:
        return {'level': 'no_data', 'label': '暂无数据', 'color': '#6c757d'}
    if correct_rate >= 85:
        return {'level': 'excellent', 'label': '优秀', 'color': '#198754'}
    elif correct_rate >= 70:
        return {'level': 'good', 'label': '良好', 'color': '#0d6efd'}
    elif correct_rate >= 60:
        return {'level': 'average', 'label': '一般', 'color': '#ffc107'}
    elif correct_rate >= 40:
        return {'level': 'weak', 'label': '薄弱', 'color': '#fd7e14'}
    else:
        return {'level': 'severe_weak', 'label': '严重薄弱', 'color': '#dc3545'}


def _get_students_by_category(category, value):
    """按分类获取学生ID列表"""
    query = User.query.filter(
        User.role == 'student',
        User.is_active == True
    )
    if category == 'class_name':
        query = query.filter(User.class_name == value)
    else:
        query = query.filter(User.major == value)
    return [s.id for s in query.all()]


def _get_category_options(category):
    """获取分类选项列表（班级名或专业名）"""
    code = 'class_name' if category == 'class_name' else 'major'
    items = DictionaryItem.get_options(code)
    options = [item.value for item in items]
    # 也加入数据库中实际存在但不在字典中的值
    field = User.class_name if category == 'class_name' else User.major
    existing = db.session.query(field).filter(
        User.role == 'student',
        User.is_active == True,
        field.isnot(None),
        field != ''
    ).distinct().all()
    for val in existing:
        if val[0] and val[0] not in options:
            options.append(val[0])
    return options


def _generate_suggestion_text(mastery_level, chapter_name, correct_rate):
    """根据掌握等级生成建议文本"""
    template = SUGGESTION_TEMPLATES.get(mastery_level, '')
    return template.format(chapter=chapter_name)


# ==================== 核心方法 ====================

def get_knowledge_overview(category, value, subject_id, time_range='30d'):
    """获取知识点掌握度概览
    
    Args:
        category: 分类维度 'class_name' 或 'major'
        value: 具体班级名或专业名
        subject_id: 学科ID
        time_range: 时间范围 '7d'/'30d'/'90d'/'all'
    
    Returns:
        dict: 包含章节掌握度列表、薄弱章节统计、教学建议
    """
    start_date = _get_time_start(time_range)
    student_ids = _get_students_by_category(category, value)
    
    if not student_ids:
        return {
            'category': category,
            'value': value,
            'subject': None,
            'chapters': [],
            'weak_count': 0,
            'severe_weak_count': 0,
            'suggestions': []
        }
    
    # 获取学科信息
    subject = Subject.query.get(subject_id)
    if not subject:
        return {'error': '学科不存在'}
    
    # 获取该学科下所有章节
    chapters = Chapter.query.filter_by(subject_id=subject_id, is_active=True).order_by(Chapter.level, Chapter.order).all()
    
    # 获取该学科下所有题目的章节映射
    question_chapters = {}
    questions_in_subject = Question.query.filter_by(subject_id=subject_id, is_active=True).all()
    for q in questions_in_subject:
        question_chapters[q.id] = q.chapter_id
    
    question_ids = list(question_chapters.keys())
    
    if not question_ids:
        chapters_data = []
        for ch in chapters:
            mastery = _calculate_mastery_level(None)
            chapters_data.append({
                'chapter_id': ch.id,
                'chapter_name': ch.name,
                'full_path': ch.get_full_path() if hasattr(ch, 'get_full_path') else ch.name,
                'level': ch.level,
                'total_answers': 0,
                'correct_count': 0,
                'correct_rate': None,
                'mastery_level': mastery['level'],
                'mastery_label': mastery['label'],
                'mastery_color': mastery['color']
            })
        return {
            'category': category,
            'value': value,
            'subject': {'id': subject.id, 'name': subject.name},
            'chapters': chapters_data,
            'weak_count': 0,
            'severe_weak_count': 0,
            'suggestions': []
        }
    
    # 按章节聚合答题数据
    answer_query = db.session.query(
        UserAnswer.question_id,
        db.func.count(UserAnswer.id).label('total'),
        db.func.sum(db.case((UserAnswer.is_correct == True, 1), else_=0)).label('correct')
    ).filter(
        UserAnswer.user_id.in_(student_ids),
        UserAnswer.question_id.in_(question_ids)
    )
    if start_date:
        answer_query = answer_query.filter(UserAnswer.created_at >= start_date)
    answer_results = answer_query.group_by(UserAnswer.question_id).all()
    
    # 按章节汇总
    chapter_stats = {}
    for ch in chapters:
        chapter_stats[ch.id] = {'total': 0, 'correct': 0}
    
    for r in answer_results:
        ch_id = question_chapters.get(r.question_id)
        if ch_id and ch_id in chapter_stats:
            chapter_stats[ch_id]['total'] += r.total
            chapter_stats[ch_id]['correct'] += r.correct
    
    # 组装章节数据
    chapters_data = []
    weak_chapters = []
    
    for ch in chapters:
        stats = chapter_stats.get(ch.id, {'total': 0, 'correct': 0})
        total = stats['total']
        correct = stats['correct']
        
        if total > 0:
            correct_rate = round(correct / total * 100, 1)
        else:
            correct_rate = None
        
        mastery = _calculate_mastery_level(correct_rate)
        
        chapter_data = {
            'chapter_id': ch.id,
            'chapter_name': ch.name,
            'full_path': ch.get_full_path() if hasattr(ch, 'get_full_path') else ch.name,
            'level': ch.level,
            'total_answers': total,
            'correct_count': correct,
            'correct_rate': correct_rate,
            'mastery_level': mastery['level'],
            'mastery_label': mastery['label'],
            'mastery_color': mastery['color']
        }
        chapters_data.append(chapter_data)
        
        # 收集薄弱章节
        if correct_rate is not None and correct_rate < 60:
            weak_chapters.append(chapter_data)
    
    # 生成教学建议
    suggestions = get_teaching_suggestions(weak_chapters)
    
    # 统计薄弱章节
    weak_count = len(weak_chapters)
    severe_weak_count = len([w for w in weak_chapters if w['correct_rate'] is not None and w['correct_rate'] < 40])
    
    return {
        'category': category,
        'value': value,
        'subject': {'id': subject.id, 'name': subject.name},
        'chapters': chapters_data,
        'weak_count': weak_count,
        'severe_weak_count': severe_weak_count,
        'suggestions': suggestions
    }


def get_chapter_detail(chapter_id, category, value, time_range='30d'):
    """获取章节钻取详情
    
    Args:
        chapter_id: 章节ID
        category: 分类维度
        value: 分类值
        time_range: 时间范围
    
    Returns:
        dict: 包含题目错误率排名、高频错题、学生分布
    """
    start_date = _get_time_start(time_range)
    student_ids = _get_students_by_category(category, value)
    
    chapter = Chapter.query.get(chapter_id)
    if not chapter:
        return {'error': '章节不存在'}
    
    # 获取该章节下所有题目
    questions = Question.query.filter_by(chapter_id=chapter_id, is_active=True).all()
    question_ids = [q.id for q in questions]
    
    if not student_ids or not question_ids:
        return {
            'chapter': {
                'id': chapter.id,
                'name': chapter.name,
                'full_path': chapter.get_full_path() if hasattr(chapter, 'get_full_path') else chapter.name
            },
            'questions': [],
            'student_distribution': {'correct': 0, 'wrong': 0, 'not_answered': 0, 'total': len(student_ids)},
            'total_students': len(student_ids)
        }
    
    # 按题目聚合答题数据
    answer_query = db.session.query(
        UserAnswer.question_id,
        db.func.count(UserAnswer.id).label('total'),
        db.func.sum(db.case((UserAnswer.is_correct == True, 1), else_=0)).label('correct')
    ).filter(
        UserAnswer.user_id.in_(student_ids),
        UserAnswer.question_id.in_(question_ids)
    )
    if start_date:
        answer_query = answer_query.filter(UserAnswer.created_at >= start_date)
    answer_results = answer_query.group_by(UserAnswer.question_id).all()
    
    answer_map = {r.question_id: {'total': r.total, 'correct': r.correct} for r in answer_results}
    
    # 获取错误原因分布（从WrongQuestion聚合）
    wrong_reason_query = db.session.query(
        WrongQuestion.question_id,
        WrongQuestion.wrong_reason,
        db.func.count(WrongQuestion.id).label('count')
    ).filter(
        WrongQuestion.user_id.in_(student_ids),
        WrongQuestion.question_id.in_(question_ids)
    ).group_by(WrongQuestion.question_id, WrongQuestion.wrong_reason).all()
    
    wrong_reason_map = {}
    for r in wrong_reason_query:
        if r.question_id not in wrong_reason_map:
            wrong_reason_map[r.question_id] = {}
        if r.wrong_reason:
            wrong_reason_map[r.question_id][r.wrong_reason] = r.count
    
    # 组装题目数据
    questions_data = []
    for q in questions:
        stats = answer_map.get(q.id, {'total': 0, 'correct': 0})
        total = stats['total']
        correct = stats['correct']
        wrong = total - correct
        
        if total > 0:
            error_rate = round(wrong / total * 100, 1)
        else:
            error_rate = None
        
        is_high_freq = error_rate is not None and error_rate >= HIGH_FREQ_ERROR_THRESHOLD
        
        # 错误原因分布
        reasons = wrong_reason_map.get(q.id, {})
        total_reasons = sum(reasons.values()) if reasons else 0
        reason_distribution = {}
        if total_reasons > 0:
            for reason, count in reasons.items():
                reason_distribution[reason] = round(count / total_reasons * 100, 1)
        
        # 题目内容摘要
        content_summary = (q.content[:80] + '...') if q.content and len(q.content) > 80 else (q.content or '')
        
        difficulty_labels = {1: '简单', 2: '中等', 3: '困难', 4: '极难'}
        
        questions_data.append({
            'question_id': q.id,
            'content_summary': content_summary,
            'content': q.content or '',
            'difficulty': q.difficulty,
            'difficulty_label': difficulty_labels.get(q.difficulty, '未知'),
            'question_type': q.question_type,
            'correct_answer': q.correct_answer or '',
            'total_answers': total,
            'correct_count': correct,
            'wrong_count': wrong,
            'error_rate': error_rate,
            'is_high_freq': is_high_freq,
            'error_reasons': reason_distribution
        })
    
    # 按错误率降序排序
    questions_data.sort(key=lambda x: x['error_rate'] if x['error_rate'] is not None else -1, reverse=True)
    
    # 计算学生答题分布
    # 统计有多少学生至少答过该章节的一道题
    students_answered = db.session.query(
        UserAnswer.user_id
    ).filter(
        UserAnswer.user_id.in_(student_ids),
        UserAnswer.question_id.in_(question_ids)
    )
    if start_date:
        students_answered = students_answered.filter(UserAnswer.created_at >= start_date)
    answered_user_ids = set(r[0] for r in students_answered.distinct().all())
    
    # 答对至少一题的学生
    students_correct = db.session.query(
        UserAnswer.user_id
    ).filter(
        UserAnswer.user_id.in_(student_ids),
        UserAnswer.question_id.in_(question_ids),
        UserAnswer.is_correct == True
    )
    if start_date:
        students_correct = students_correct.filter(UserAnswer.created_at >= start_date)
    correct_user_ids = set(r[0] for r in students_correct.distinct().all())
    
    # 答错至少一题（且没有全对）的学生
    students_wrong = db.session.query(
        UserAnswer.user_id
    ).filter(
        UserAnswer.user_id.in_(student_ids),
        UserAnswer.question_id.in_(question_ids),
        UserAnswer.is_correct == False
    )
    if start_date:
        students_wrong = students_wrong.filter(UserAnswer.created_at >= start_date)
    wrong_user_ids = set(r[0] for r in students_wrong.distinct().all())
    
    # 分类：全对、有错、未答
    all_correct = correct_user_ids - wrong_user_ids
    has_wrong = wrong_user_ids
    not_answered = set(student_ids) - answered_user_ids
    
    student_distribution = {
        'correct': len(all_correct),
        'wrong': len(has_wrong),
        'not_answered': len(not_answered),
        'total': len(student_ids)
    }
    
    return {
        'chapter': {
            'id': chapter.id,
            'name': chapter.name,
            'full_path': chapter.get_full_path() if hasattr(chapter, 'get_full_path') else chapter.name
        },
        'questions': questions_data,
        'student_distribution': student_distribution,
        'total_students': len(student_ids)
    }


def get_comparison_data(category, subject_id, time_range='30d'):
    """获取班级/专业对比数据
    
    Args:
        category: 分类维度
        subject_id: 学科ID
        time_range: 时间范围
    
    Returns:
        dict: 各分类在各章节的掌握度对比
    """
    start_date = _get_time_start(time_range)
    
    subject = Subject.query.get(subject_id)
    if not subject:
        return {'error': '学科不存在'}
    
    # 获取所有分类值
    category_values = _get_category_options(category)
    
    if len(category_values) < 2:
        return {
            'categories': category_values,
            'chapters': [],
            'message': '至少需要2个分类才能进行对比'
        }
    
    # 获取章节列表
    chapters = Chapter.query.filter_by(subject_id=subject_id, is_active=True).order_by(Chapter.level, Chapter.order).all()
    
    # 获取题目-章节映射
    questions_in_subject = Question.query.filter_by(subject_id=subject_id, is_active=True).all()
    question_chapters = {q.id: q.chapter_id for q in questions_in_subject}
    question_ids = list(question_chapters.keys())
    
    if not question_ids:
        return {
            'categories': category_values,
            'chapters': [],
            'subject': {'id': subject.id, 'name': subject.name}
        }
    
    # 对每个分类查询各章节掌握度
    comparison_data = []
    
    for ch in chapters:
        ch_question_ids = [qid for qid, cid in question_chapters.items() if cid == ch.id]
        if not ch_question_ids:
            continue
        
        chapter_comparison = {
            'chapter_id': ch.id,
            'chapter_name': ch.name,
            'full_path': ch.get_full_path() if hasattr(ch, 'get_full_path') else ch.name,
            'rates': {},
            'max_diff': 0,
            'has_significant_diff': False
        }
        
        rates = []
        for cat_value in category_values:
            student_ids = _get_students_by_category(category, cat_value)
            if not student_ids:
                chapter_comparison['rates'][cat_value] = None
                continue
            
            # 查询该分类学生在该章节的答题统计
            answer_query = db.session.query(
                db.func.count(UserAnswer.id).label('total'),
                db.func.sum(db.case((UserAnswer.is_correct == True, 1), else_=0)).label('correct')
            ).filter(
                UserAnswer.user_id.in_(student_ids),
                UserAnswer.question_id.in_(ch_question_ids)
            )
            if start_date:
                answer_query = answer_query.filter(UserAnswer.created_at >= start_date)
            result = answer_query.first()
            
            if result and result.total > 0:
                rate = round(result.correct / result.total * 100, 1)
            else:
                rate = None
            
            chapter_comparison['rates'][cat_value] = rate
            if rate is not None:
                rates.append(rate)
        
        # 计算最大差异
        if len(rates) >= 2:
            max_diff = round(max(rates) - min(rates), 1)
            chapter_comparison['max_diff'] = max_diff
            chapter_comparison['has_significant_diff'] = max_diff > SIGNIFICANT_DIFF_THRESHOLD
        
        # 计算平均掌握度
        if rates:
            chapter_comparison['avg_rate'] = round(sum(rates) / len(rates), 1)
        else:
            chapter_comparison['avg_rate'] = None
        
        comparison_data.append(chapter_comparison)
    
    return {
        'categories': category_values,
        'chapters': comparison_data,
        'subject': {'id': subject.id, 'name': subject.name}
    }


def get_weak_chapters(category, value, subject_id, time_range='30d'):
    """获取薄弱知识点预警
    
    Args:
        category: 分类维度
        value: 分类值
        subject_id: 学科ID
        time_range: 时间范围
    
    Returns:
        dict: 薄弱章节列表
    """
    overview = get_knowledge_overview(category, value, subject_id, time_range)
    if 'error' in overview:
        return overview
    
    weak_chapters = []
    severe_weak_chapters = []
    
    for ch in overview['chapters']:
        rate = ch['correct_rate']
        if rate is None:
            continue
        if rate < 40:
            ch['severity'] = 'severe_weak'
            severe_weak_chapters.append(ch)
            weak_chapters.append(ch)
        elif rate < 60:
            ch['severity'] = 'weak'
            weak_chapters.append(ch)
    
    # 按正确率升序排序
    weak_chapters.sort(key=lambda x: x['correct_rate'] if x['correct_rate'] is not None else 999)
    
    return {
        'weak_chapters': weak_chapters,
        'severe_weak_chapters': severe_weak_chapters,
        'weak_count': len(weak_chapters),
        'severe_weak_count': len(severe_weak_chapters)
    }


def get_teaching_suggestions(weak_chapters):
    """生成教学建议
    
    Args:
        weak_chapters: 薄弱章节列表（包含correct_rate和chapter_name）
    
    Returns:
        list: 教学建议列表（最多5条）
    """
    if not weak_chapters:
        return []
    
    # 按正确率升序排序
    sorted_weak = sorted(weak_chapters, key=lambda x: x.get('correct_rate', 999))
    
    # 取前5条
    top_weak = sorted_weak[:5]
    
    suggestions = []
    for i, ch in enumerate(top_weak):
        rate = ch.get('correct_rate', 0)
        mastery = _calculate_mastery_level(rate)
        level = mastery['level']
        
        action = _generate_suggestion_text(level, ch['chapter_name'], rate)
        if not action:
            continue
        
        suggestions.append({
            'priority': i + 1,
            'chapter_name': ch['chapter_name'],
            'chapter_id': ch.get('chapter_id'),
            'correct_rate': rate,
            'action': action,
            'mastery_level': level,
            'mastery_label': mastery['label']
        })
    
    return suggestions
