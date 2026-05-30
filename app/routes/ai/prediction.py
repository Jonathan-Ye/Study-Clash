import logging
import threading
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app import socketio
from app.services.ai.prediction_service import PredictionService
from app.services.ai.task_manager import TaskManager

logger = logging.getLogger(__name__)
ai_prediction_bp = Blueprint('ai_prediction', __name__)


@ai_prediction_bp.route('/trigger', methods=['POST'])
@login_required
def trigger_prediction():
    task = TaskManager.create_task('prediction', current_user.id)
    thread = threading.Thread(target=_run_prediction, args=(current_user.id, task.id), daemon=True)
    thread.start()
    return jsonify({
        'status': 'started',
        'task_id': task.id,
        'message': '推理预测已触发',
    })


def _run_prediction(user_id, task_id):
    try:
        with socketio.server.app.app_context():
            TaskManager.update_task_progress(task_id, 5, '推理预测启动中')
            PredictionService.predict(user_id, task_id)
    except Exception as e:
        logger.error(f'推理预测后台任务异常: {e}', exc_info=True)
        try:
            with socketio.server.app.app_context():
                TaskManager.fail_task(task_id, str(e))
        except Exception:
            pass


@ai_prediction_bp.route('/result', methods=['GET'])
@login_required
def get_prediction_result():
    user_id = current_user.id
    if current_user.is_admin and request.args.get('user_id'):
        user_id = int(request.args.get('user_id'))
    result = PredictionService.get_result(user_id)
    return jsonify(result)


@ai_prediction_bp.route('/task-status', methods=['GET'])
@login_required
def get_task_status():
    task_id = request.args.get('task_id', type=int)
    if not task_id:
        return jsonify({'error': '缺少task_id参数'}), 400
    task = TaskManager.get_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404
    return jsonify({
        'task_id': task.id,
        'task_type': task.task_type,
        'status': task.status,
        'progress': task.progress,
        'message': task.message,
    })
