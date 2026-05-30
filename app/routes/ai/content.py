from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app.services.ai.content_service import ContentService

ai_content_bp = Blueprint('ai_content', __name__)


@ai_content_bp.route('/explanation', methods=['POST'])
@login_required
def generate_explanation():
    data = request.get_json()
    question_id = data.get('question_id')
    if not question_id:
        return jsonify({'error': '缺少question_id'}), 400
    result = ContentService.generate_explanation(question_id, current_user.id)
    return jsonify(result)


@ai_content_bp.route('/variant-questions', methods=['POST'])
@login_required
def generate_variant_questions():
    data = request.get_json()
    question_id = data.get('question_id')
    if not question_id:
        return jsonify({'error': '缺少question_id'}), 400
    result = ContentService.generate_variant_questions(question_id, current_user.id)
    return jsonify(result)


@ai_content_bp.route('/practice', methods=['POST'])
@login_required
def generate_practice():
    data = request.get_json()
    knowledge_point = data.get('knowledge_point')
    if not knowledge_point:
        return jsonify({'error': '缺少knowledge_point'}), 400
    difficulty = data.get('difficulty', 2)
    result = ContentService.generate_practice(knowledge_point, current_user.id, difficulty)
    return jsonify(result)
