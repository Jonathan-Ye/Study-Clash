from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app import db, csrf
from app.models import Subject, Chapter, Question, User, GameRecord
from app.models.question_feedback import QuestionFeedback
from datetime import datetime, timezone

api_bp = Blueprint('api', __name__)

@api_bp.route('/subjects')
@login_required
def get_subjects():
    subjects = Subject.query.filter_by(is_active=True).all()
    
    user_major = getattr(current_user, 'major', None) if current_user.is_authenticated else None
    
    filtered_subjects = [
        s for s in subjects 
        if s.is_applicable_for_major(user_major)
    ]
    
    return jsonify([{
        'id': s.id,
        'name': s.name,
        'icon': s.icon,
        'chapter_count': s.chapters.count(),
        'question_count': s.questions.count()
    } for s in filtered_subjects])

@api_bp.route('/subjects/<int:subject_id>/chapters')
@login_required
def get_chapters(subject_id):
    chapters = Chapter.query.filter_by(subject_id=subject_id, is_active=True).order_by(Chapter.order.asc()).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'order': c.order,
        'question_count': c.questions.count()
    } for c in chapters])

@api_bp.route('/questions/random')
@login_required
def get_random_questions():
    subject_id = request.args.get('subject_id', type=int)
    chapter_id = request.args.get('chapter_id', type=int)
    difficulty = request.args.get('difficulty', type=int)
    count = request.args.get('count', 10, type=int)
    
    user_major = getattr(current_user, 'major', None) if current_user.is_authenticated else None
    
    from app.services.game_service import get_random_questions as svc_get_random
    questions = svc_get_random(subject_id, chapter_id, count, difficulty, user_major)
    
    return jsonify([q.to_dict() for q in questions])

@api_bp.route('/questions/<int:question_id>')
@login_required
def get_question(question_id):
    question = Question.query.get_or_404(question_id)
    include_answer = request.args.get('include_answer', 'false').lower() == 'true'
    return jsonify(question.to_dict(include_answer=include_answer))

@api_bp.route('/users/<int:user_id>')
@login_required
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())

@api_bp.route('/users/search')
@login_required
def search_users():
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    
    users = User.query.filter(
        User.is_active == True,
        db.or_(
            User.username.contains(query),
            User.nickname.contains(query)
        )
    ).limit(10).all()
    
    return jsonify([{
        'id': u.id,
        'username': u.username,
        'nickname': u.nickname or u.username,
        'avatar': u.avatar
    } for u in users])

@api_bp.route('/game-types')
def get_game_types():
    return jsonify([
        {'type': 'single', 'name': '单人挑战', 'max_players': 1, 'description': '独自挑战，提升自我'},
        {'type': 'battle', 'name': '双人对战', 'max_players': 2, 'description': '1v1对战，一决高下'},
        {'type': 'four', 'name': '四人挑战', 'max_players': 4, 'description': '4人大战，群雄逐鹿'}
    ])

@api_bp.route('/difficulties')
def get_difficulties():
    return jsonify([
        {'level': 1, 'name': '简单', 'description': '基础题目，适合入门'},
        {'level': 2, 'name': '中等', 'description': '进阶题目，巩固知识'},
        {'level': 3, 'name': '困难', 'description': '高难度题，挑战自我'},
        {'level': 4, 'name': '极难', 'description': '极限挑战，学霸专属'}
    ])

@api_bp.route('/health')
@csrf.exempt
def health_check():
    return jsonify({'status': 'healthy', 'message': 'Study Clash API is running'})

@api_bp.route('/feedback/submit', methods=['POST'])
@login_required
def submit_feedback():
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'message': '无效的请求数据'}), 400
    
    question_id = data.get('question_id')
    feedback_type = data.get('feedback_type')
    content = data.get('content')
    
    if not question_id or not feedback_type or not content:
        return jsonify({'success': False, 'message': '请填写完整的反馈信息'}), 400
    
    question = Question.query.get(question_id)
    if not question:
        return jsonify({'success': False, 'message': '题目不存在'}), 404
    
    if feedback_type not in QuestionFeedback.FEEDBACK_TYPES:
        return jsonify({'success': False, 'message': '无效的反馈类型'}), 400
    
    existing_feedback = QuestionFeedback.query.filter_by(
        question_id=question_id,
        user_id=current_user.id,
        status='pending'
    ).first()
    
    if existing_feedback:
        return jsonify({'success': False, 'message': '您已经对此题提交过反馈，请等待处理'}), 400
    
    feedback = QuestionFeedback(
        question_id=question_id,
        user_id=current_user.id,
        feedback_type=feedback_type,
        content=content
    )
    
    db.session.add(feedback)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': '反馈提交成功！感谢您的宝贵意见。',
        'feedback_id': feedback.id
    })
