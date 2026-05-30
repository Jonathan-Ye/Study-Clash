from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app.services.ai.chat_service import ChatService

ai_chat_bp = Blueprint('ai_chat', __name__)


@ai_chat_bp.route('/sessions', methods=['POST'])
@login_required
def create_session():
    result = ChatService.create_session(current_user.id)
    return jsonify(result)


@ai_chat_bp.route('/sessions/<int:session_id>/messages', methods=['POST'])
@login_required
def send_message(session_id):
    data = request.get_json()
    message = data.get('message', '')
    result = ChatService.send_message(session_id, message)
    return jsonify(result)


@ai_chat_bp.route('/sessions/<int:session_id>/messages', methods=['GET'])
@login_required
def get_messages(session_id):
    limit = request.args.get('limit', 20, type=int)
    result = ChatService.get_history(session_id, limit)
    return jsonify(result)


@ai_chat_bp.route('/sessions/<int:session_id>', methods=['DELETE'])
@login_required
def close_session(session_id):
    result = ChatService.close_session(session_id)
    return jsonify(result)
